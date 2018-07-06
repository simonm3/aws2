import logging as log

import fabric.api as fab
from time import sleep
import threading
from botocore.exceptions import ClientError
from . import aws, Instance

class Spot(Instance):
    """
    persistent spot instance saved as snapshot/image
    tag:Name used for instance, volume, snapshot, image
    """
    def __init__(self, res, 
                 select=None, sort=None, ip=0,
                 VolumeSize=None, security=["default"], key="key"):
        """
        launch spot and block until ready

        res: ami.id to create instance; or existing instance (name, id or aws resource)
        select: instance type or pandas query e.g. "p2.xlarge" or "memory>=15 & vcpu>=2"
        sort:  pandas sort to prioritise instance_type e.g. "percpu"
               Note SpotPrice is automatically appended to sort
        ip: ipaddress; index of elastic ip; if None then uses default.
        VolumeSize: sets volume size on launch. default is last size saved
        security: aws security groups
        key: aws ssh key name

        columns available for query/sort:
        Note inconsistent use of caps!
            ['clockSpeed', 'currentGeneration', 'dedicatedEbsThroughput', 'ecu',
           'enhancedNetworkingSupported', 'gpu', 'instanceFamily', 'InstanceType',
           'intelAvx2Available', 'intelAvxAvailable', 'intelTurboAvailable',
           'licenseModel', 'location', 'locationType', 'memory',
           'networkPerformance', 'normalizationSizeFactor', 'operatingSystem',
           'operation', 'physicalProcessor', 'preInstalledSw',
           'processorArchitecture', 'processorFeatures', 'servicecode',
           'servicename', 'storage', 'tenancy', 'usagetype', 'vcpu',
           'AvailabilityZone', 'SpotPrice', 'percpu', 'per64cpu']
        """
        super().__init__(res)

        if sort is None:
            sort = []

        # existing instance
        if self.res:
            log.info("spot instance found")
            return

        # new instance from ami
        try:
            # own ami name
            img = aws.get_images(Name=self.Name)[-1]
        except IndexError:
            # ami id (3rd party images don't have a name)
            img = aws.ec2.Image(self.Name)
            try:
                if img.state!="available":
                    raise Exception("image not available")
            except AttributeError:
                raise Exception(f"no images found for {self.Name}")

        df = aws.get_spotprices()

        # select cheapest meeting criteria
        if select in df.InstanceType.values:
            select = f"InstanceType=='{select}'"
        if select is not None:
            df = df.query(select)
        sort.append("SpotPrice")
        sel = df.sort_values(sort).iloc[0]

        # create request
        bdm = [dict(DeviceName=img.block_device_mappings[0]["DeviceName"],
                    Ebs=dict(DeleteOnTermination=False,
                             VolumeType="gp2"))]
        if VolumeSize:
            bdm[0]["Ebs"]["VolumeSize"] = VolumeSize
        spec = dict(
            ImageId=img.id,
            InstanceType=sel.InstanceType,
            KeyName=key,
            SecurityGroups=security,
            BlockDeviceMappings=bdm,
            Placement=dict(AvailabilityZone=sel.AvailabilityZone))
        log.info(f"requesting spot {sel.InstanceType} "
                f"${float(sel.SpotPrice):.2f}, "
                f"{sel.AvailabilityZone}, "
                f"memory={sel.memory}, "
                f"vcpu={sel.vcpu}")

        # launch
        self.get_spot(spec, ip)

    def get_spot(self, spec, ip):
        """ request spot
        """
        from . import Volume
        
        # check name not already being used
        instances = aws.get_instances(Name=self.Name)
        if instances:
            raise Exception(f"{self.Name} instance already exists")
        volumes = aws.get_volumes(Name=self.Name)
        if volumes:
            raise Exception(f"{self.Name} volume already exists")

        # request spot
        r = aws.client.request_spot_instances(LaunchSpecification=spec)
        requestId = r["SpotInstanceRequests"][0]['SpotInstanceRequestId']
        try:
            waiter = aws.client.get_waiter('spot_instance_request_fulfilled')
            waiter.wait(SpotInstanceRequestIds=[requestId])
        except Exception:
            raise Exception("problem launching spot instance")
        instanceId = aws.client.describe_spot_instance_requests(
            SpotInstanceRequestIds=[requestId])[
            'SpotInstanceRequests'][0]['InstanceId']
        self.res = aws.ec2.Instance(instanceId)
        self.Name = self._Name

        # wait until running
        log.info("instance starting")
        self.wait_until_running()
        self.set_ip(ip)
        
        # post-launch
        volume = Volume(list(self.volumes.all())[0])
        volume.Name = self.Name
        fab.sudo("cp /usr/share/zoneinfo/Europe/London /etc/localtime")
        self.optimise()

        # start spot termination thread
        p = threading.Thread(target=self.spotcheck, args=[
                             self.spot_instance_request_id, self.stop])
        p.start()

    def spotcheck(self, requestId, callback):
        """ poll for spot request termination notice

        requestId: spot request to poll
        callback: callback function when notice received
        """
        while True:
            try:
                requests = aws.client.describe_spot_instance_requests(
                    SpotInstanceRequestIds=[requestId])
                request = requests['SpotInstanceRequests'][0]
            except (ClientError, IndexError):
                log.warning(
                    "spot request not found. instance probably terminated.")
                return

            # instance marked for termination
            if request["Status"]["Code"] == "marked-for-termination":
                log.warning("spot request marked for termination by amazon. "
                            "attempting to save volume as snapshot")

                log.info(f"terminating {self.Name}")
                callback(self)
                return

            # instance terminated in some other way
            if request["Status"]["Code"] not in \
                        ["fulfilled", "instance-terminated-by-user"]:
                log.info("spot status is %s" % request["Status"]["Code"])
                return

            # amazon recommend poll every 5 seconds
            sleep(5)

    def stop(self, save=True, termfirst=True):
        """ terminate instance and save as snapshot/image. block until saved.
        save=False terminates without saving
        termfirst=True terminate then save volume (faster/cheaper. some things don't work e.g. ena)
        termfirst=False save then terminate (AWS recommended)
        """
        from . import Volume

        if save==False:
            self.terminate(delete_volume=True)
            return

        if termfirst:
            # terminate
            volume = Volume(self.Name)
            self.terminate()

            # save
            volume.create_image()
            volume.delete()
        else:
            # save and terminate
            self.create_image()
            self.terminate(delete_volume=True)

    def terminate(self, delete_volume=False):
        """ terminate with option to force delete volume """
        from . import Volume
        
        volume = Volume(self.Name)
        self.Name = ""
        try:
            self.res.terminate()
        except ClientError:
            log.warning("Instance could not be terminated. May not exist")
        if delete_volume:
            volume.delete()

    def create_image_ena(self, name=None):
        log.warning("Cannot create ena image from spot instance")