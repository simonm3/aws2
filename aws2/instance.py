import logging as log

import fabric
import fabric.api as fab
from time import sleep
import pyperclip
import requests
import uuid
from . import aws, Resource


def copyclip(text):
    """ copy to clipboard """
    try:
        pyperclip.copy(text)
    except Exception:
        log.warning("pyperclip cannot find copy/paste mechanism")


class Instance(Resource):

    def __init__(self, res):
        self.coll = aws.get_instances
        super().__init__(res)
        try:
            fab.env.host_string = self.res.public_ip_address
        except AttributeError:
            pass
    
    def start(self, instance_type="t2.micro"):
        """ blocking start of new instance """
        if self.res is not None:
            self.res.start()
        else:
            img = aws.get_images(Name=self.Name)[-1]
            bdm = [dict(DeviceName=img.block_device_mappings[0]["DeviceName"],
                        Ebs=dict(DeleteOnTermination=True,
                                 VolumeType="gp2"))]
            self.res = aws.ec2.create_instances(ImageId=img.id,
                                                InstanceType=instance_type,
                                                BlockDeviceMappings=bdm,
                                                MinCount=1, MaxCount=1,
                                                KeyName="key",
                                                SecurityGroups=["simon"])[0]
            # update aws name
            self.Name = self.Name

        log.info("waiting for instance running")
        self.wait_until_running()
        fab.env.host_string = self.public_ip_address
        self.wait_ssh()

    def stop(self):
        """ blocking stop """
        self.res.stop()
        waiter = aws.client.get_waiter("instance_stopped")
        log.info(f"waiting for instance stopped")
        waiter.wait(InstanceIds=[self.id])

    def terminate(self):
        """ release name and terminate """
        self.Name = ""
        self.res.terminate()

    def create_image(self, name=None):
        """ blocking save to image
        name: saved image name. default self.Name
        """
        from . import Image, Snapshot
        
        if name is None:
            name = self.Name

        # create image from instance (creating from volume does not retain ena)
        image = Image(self.res.create_image(Name=str(uuid.uuid4())))
        log.info("waiting for image to be saved")
        image.wait_until_exists(Filters=aws.filt(state='available'))
        image.Name = name
        log.info("image saved")

        # name the snapshot
        snapshotid = image.block_device_mappings[0]["Ebs"]["SnapshotId"]
        snapshot = Snapshot(snapshotid)
        snapshot.Name = name

        # deregister all except latest
        images = aws.get_images(Name=name)
        for image in images[:-1]:
            aws.client.deregister_image(ImageId=image.id)

    def create_image_ena(self, name=None):
        """ create image with ena from instance that does not have it """
        if name is None:
            name = self.Name
        self.stop()
        self.modify_attribute(InstanceType=dict(Value="c5.large"))
        self.modify_attribute(EnaSupport=dict(Value=True))
        self.create_image(name=name)
        self.terminate()

    def optimise(self):
        """ optimse settings for gpu
        https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/accelerated-computing-instances.html#optimize_gpu
        """
        if not self.instance_type.startswith(("p2", "p3", "g3")):
            return

        fab.sudo("nvidia-smi --auto-boost-default=0")
        if self.instance_type.startswith("P2"):
            fab.sudo("nvidia-smi -ac 2505,875")
        elif self.instance_type.startswith("P3"):
            fab.sudo("sudi nvidia-smi -ac 877,1530")
        elif self.instance_type.startswith("P3"):
            fab.sudo("nvidia-smi -ac 2505,1177")

    def run(self, command):
        fab.env.host_string = self.res.public_ip_address
        return fab.run(command)

    def set_ip(self, ip=0):
        """ sets ip address
        ip: ipaddress or index of elastic ip """
        if isinstance(ip, int):
            ip = aws.get_ips()[ip]
        if ip is not None:
            fab.env.host_string = ip
            aws.client.associate_address(InstanceId=self.id, PublicIp=ip)
        self.wait_ssh()
        copyclip(ip)

    def jupyter(self):
        """ launch jupyter notebook server """
        self.run("./jupyter.sh")
        self.wait_notebook()

    # waiters #######################################################

    def wait_ssh(self):
        """ block until ssh available """
        log.info(f"ssh server starting {fab.env.host_string}")
        while True:
            try:
                with fab.quiet():
                    r = fab.sudo("ls")
                    if r.succeeded:
                        break
            except Exception:
                pass
            sleep(1)

    def wait_notebook(self):
        """ block until notebook available """
        address = f"{fab.env.host_string}:8888"
        copyclip(address)
        log.info(f"jupyter notebook server starting {address}")
        while True:
            try:
                r = requests.get(f"http://{address}")
                if r.status_code == 200:
                    break
            except fabric.exceptions.NetworkError:
                pass
            except Exception:
                pass
            sleep(5)
