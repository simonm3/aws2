import logging
from time import sleep
import threading
from . import aws, Instance

log = logging.getLogger(__name__)


class Spot(Instance):
    """
    spot instance is saved as a snapshot/image with same name
    multiple versions of images/snapshots with the same name represent different versions. delete to rollback.
    instance name is unique and reset on termination. otherwise there would be a conflict saving snapshots and images
    
    # todo review spot versus instance. could be thinner instance?
    """
    def get_spec(self, name, instance_type, specfile):
        spec = super().get_spec(name, instance_type, specfile)
        spec.pop("MinCount", "")
        spec.pop("MaxCount", "")
        return spec

    def create(self, spec):
        """ create spot instance with spec
        :param spec: dict definition of instance
        :return: running aws.ec2.Instance
        """
        log.info("requesting spot")
        r = aws.client.request_spot_instances(LaunchSpecification=spec)
        requestId = r["SpotInstanceRequests"][0]["SpotInstanceRequestId"]
        try:
            waiter = aws.client.get_waiter("spot_instance_request_fulfilled")
            waiter.wait(SpotInstanceRequestIds=[requestId])
        except Exception:
            raise Exception("problem launching spot instance")
        instanceId = aws.client.describe_spot_instance_requests(
            SpotInstanceRequestIds=[requestId]
        )["SpotInstanceRequests"][0]["InstanceId"]
        res = aws.ec2.Instance(instanceId)
        log.info("wait until running")
        res.wait_until_running()

        # spot termination thread
        p = threading.Thread(target=self.spotcheck, args=[requestId, self.stop])
        p.start()

        return res

    def spotcheck(self, requestId, callback):
        """ poll for spot request termination notice

        :param requestId: spot request to poll
        :param callback: callback function when notice received
        """
        while True:
            try:
                requests = aws.client.describe_spot_instance_requests(
                    SpotInstanceRequestIds=[requestId]
                )
                request = requests["SpotInstanceRequests"][0]
            except:
                # spot request not found. instance probably terminated.
                # keep going just in case. if already terminated then costs nothing!
                pass

            # instance marked for termination
            if request["Status"]["Code"] == "marked-for-termination":
                log.warning(
                    "spot request marked for termination by amazon. "
                    "attempting to save volume as snapshot"
                )

                log.info(f"terminating {self.name}")
                callback(self)
                return

            # instance terminated in some other way
            if request["Status"]["Code"] not in [
                "fulfilled",
                "instance-terminated-by-user",
            ]:
                log.info("spot status is %s" % request["Status"]["Code"])
                return

            # amazon recommend poll every 5 seconds
            sleep(5)

    def terminate(self, save=True, ena=False):
        """ terminate instance and save as snapshot/image. block until saved.
        :param ena: True sets ena. time consuming as uses hack below.

        sometimes want to use cheap spot for setup then switch to ena
        ena cannot be turned on from a running instance and spot instances cannot be stopped.
        hack is to save spot; create new instance; stop it; set ena; save it.
        """
        from . import Image

        volume = self.volumes[0]
        name = self.name
        super().terminate()
        if save:
            volume.create_image()
        volume.delete()

        # start a new instance to set ena. hack required as volume.create_image never sets ena.
        if ena:
            i = Image(name)
            i.set_ena()

    def stop(self, save=True):
        """ for spot instance this is same as terminate """
        self.terminate(save=save)
