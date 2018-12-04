import logging as log

from os.path import join, expanduser
from fabric import Connection
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

    def __init__(self, res, instance_type="t2.micro", key="key", user="ubuntu", security=["default"]):
        self.coll = aws.get_instances
        super().__init__(res)
        
        self.user = user
        self.instance_type = instance_type
        self.key = key
        self.security = security
    
    def start(self):
        """ blocking start of new instance """
        from . import Volume

        if self.res is not None:
            self.res.start()
        else:
            img = aws.get_images(Name=self.Name)[-1]
            bdm = [dict(DeviceName=img.block_device_mappings[0]["DeviceName"],
                        Ebs=dict(DeleteOnTermination=True,
                                 VolumeType="gp2"))]
            self.res = aws.ec2.create_instances(ImageId=img.id,
                                                InstanceType=self.instance_type,
                                                BlockDeviceMappings=bdm,
                                                MinCount=1, MaxCount=1,
                                                KeyName=self.key,
                                                SecurityGroups=self.security)[0]
            # update aws name
            self.Name = self.Name

        log.info("instance starting")
        self.wait_until_running()
        self.connect()
        self.wait_ssh()

        # post-launch
        volume = Volume(list(self.volumes.all())[0])
        volume.Name = self.Name
        self.sudo("cp /usr/share/zoneinfo/Europe/London /etc/localtime")
        self.optimise()

    def connect(self):
        self.connection = Connection(self.public_ip_address, user=self.user, 
                                     connect_kwargs=dict(key_filename=join(expanduser("~"), ".aws/key.pem")))

    def stop(self, save=False, ena=False):
        """ blocking stop

         ena=True sets ena
         save=True saves snapshot/image
        """
        # stop
        self.res.stop()
        waiter = aws.client.get_waiter("instance_stopped")
        log.info(f"stopping instance")
        waiter.wait(InstanceIds=[self.id])

        # enable ena if required
        if ena:
            log.info("enabling ena")
            self.modify_attribute(InstanceType=dict(Value="c5.large"))
            self.modify_attribute(EnaSupport=dict(Value=True))

        if save:
            self.create_image()
            self.terminate()

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
        log.info("saving image")
        image.wait_until_exists(Filters=aws.filt(state='available'))
        image.Name = name

        # name the snapshot and count
        snapshotid = image.block_device_mappings[0]["Ebs"]["SnapshotId"]
        snapshot = Snapshot(snapshotid)
        snapshot.Name = name
        snapcount = len(aws.get_snapshots(Name=name))
        log.info(f"You now have {snapcount} {name} snapshots")

        # deregister all except latest
        images = aws.get_images(Name=name)
        for image in images[:-1]:
            aws.client.deregister_image(ImageId=image.id)

    def optimise(self):
        """ optimse settings for gpu
        https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/accelerated-computing-instances.html#optimize_gpu
        """
        if not self.instance_type.startswith(("p2", "p3", "g3")):
            return

        c = self.connection

        c.sudo("nvidia-smi --auto-boost-default=0")
        if self.instance_type.startswith("P2"):
            c.sudo("nvidia-smi -ac 2505,875")
        elif self.instance_type.startswith("P3"):
            c.sudo("sudi nvidia-smi -ac 877,1530")
        elif self.instance_type.startswith("P3"):
            c.sudo("nvidia-smi -ac 2505,1177")

    def run(self, *args, **kwargs):
        return self.connection.run(*args, **kwargs)

    def sudo(self, *args, **kwargs):
        return self.connection.sudo(*args, **kwargs)

    def set_ip(self, ip=0):
        """ sets ip address
        ip: ipaddress or index of elastic ip """
        if isinstance(ip, int):
            ip = aws.get_ips()[ip]
        if ip is not None:
            aws.client.associate_address(InstanceId=self.id, PublicIp=ip)
        self.connect()
        self.wait_ssh()
        copyclip(ip)

    def jupyter(self):
        """ launch jupyter notebook server """
        self.run("./jupyter.sh")
        self.wait_notebook()

    # waiters #######################################################

    def wait_ssh(self):
        """ block until ssh available """
        log.info(f"ssh server starting {self.public_ip_address}")
        while True:
            try:
                r = self.run("ls", hide="stdout")
                if r.exited==0:
                    break
            except Exception:
                pass
            sleep(1)

    def wait_notebook(self):
        """ block until notebook available """
        address = f"{self.public_ip_address}:8888"
        copyclip(address)
        log.info(f"jupyter notebook server starting {address}")
        while True:
            try:
                r = requests.get(f"http://{address}")
                if r.status_code == 200:
                    break
                sleep(5)
            except:
                pass
