from os.path import join, expanduser
from fabric import Connection
from time import sleep
import pyperclip
import requests
import uuid
import yaml
import os
from . import aws, Resource
import logging

log = logging.getLogger(__name__)

HERE = os.path.dirname(__file__)

class Instance(Resource):
    """ aws instance resource """

    def __init__(self, res, instance_type=None, specfile=None, user="ubuntu"):
        """
        wrap aws.ec2.Instance or start a new one

        :param res: name, id, aws.ec2.Instance, Instance
        :param instance_type: overrides the instance type in spec
        :param specfile: optional aws instance specification. if None then f"{res}.yaml" or default.yaml
        :param user: username for ssh connection to new instance

        Less frequently changed parameters are in specfile
        """
        self.coll = aws.get_instances
        super().__init__(res)

        # existing instance
        if self.res:
            return

        # new instance
        name = res
        spec = self.get_spec(name, instance_type, specfile)
        self.res = self.create(spec)
        self.name = name
        self.user = user
        self.connection = None
        self.post_launch()

    @property
    def user(self):
        return self.tags.get("user", "")

    @user.setter
    def user(self, value):
        self.set_tags(user=value)

    @property
    def volumes(self):
        """ return list of Volume objects """
        from . import Volume

        return [Volume(v) for v in list(self.res.volumes.all())]

    def get_spec(self, name, instance_type, specfile):
        """ load instance specification
        :return: (spec, nonaws) that are dict of aws spec and nonaws variables
        """
        if specfile:
            pass
        elif os.path.exists(f"{HERE}/{name}.yaml"):
            specfile = f"{HERE}/{name}.yaml"
        else:
            specfile = f"{HERE}/default.yaml"
        spec = yaml.safe_load(open(specfile))
        if instance_type:
            spec["InstanceType"] = instance_type
        try:
            # image found for name
            spec["ImageId"] = aws.get_images(name=name)[-1]
        except IndexError:
            pass
        return spec

    def create(self, spec):
        log.info("launching instance")
        res = aws.ec2.create_instances(**spec)[0]
        log.info("wait until running")
        res.wait_until_running()
        return res

    def post_launch(self):
        """ set tags on running instance and run setup scripts """
        self.volumes[0].name = self.name
        self.set_connection()
        self.wait_ssh()
        self.sudo("cp /usr/share/zoneinfo/Europe/London /etc/localtime")
        self.optimise()
        self.connection.close()

    def stop(self, save=False, ena=False):
        """ stop and set ena or save as image

        :param ena: sets ena
        :param save: saves snapshot/image
        """
        # stop
        log.info(f"stopping instance")
        self.res.stop()

        if ena or save:
            waiter = aws.client.get_waiter("instance_stopped")
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
        self.res.terminate()
        self.name = ""

    def create_image(self, name=None):
        """ blocking save to image
        :param name: saved image name. default self.name
        """
        from . import Image, Snapshot

        if name is None:
            name = self.name

        # create image from instance (creating from volume does not retain ena)
        log.info("saving image")
        image = Image(self.res.create_image(Name=str(uuid.uuid4())))
        image.wait_until_exists(Filters=aws.filt(state="available"))
        image.name = name

        # name the snapshot and count
        snapshotid = image.block_device_mappings[0]["Ebs"]["SnapshotId"]
        snapshot = Snapshot(snapshotid)
        snapshot.name = name
        snapcount = len(aws.get_snapshots(name=name))
        log.info(f"You now have {snapcount} {name} snapshots")

        # deregister all except latest
        images = aws.get_images(name=name)
        for image in images[:-1]:
            aws.client.deregister_image(ImageId=image.id)

    # waiters #######################################################

    def wait_ssh(self):
        """ block until ssh available """
        log.info(f"waiting for ssh {self.public_ip_address}")
        while True:
            try:
                r = self.run("runlevel", hide="stdout")
                if r.exited == 0:
                    break
            except:
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

    ############# fabric ########################################################################

    def set_connection(self):
        if not self.public_ip_address or not self.user:
            return

        try:
            self.connection.close()
        except AttributeError:
            pass

        self.connection = Connection(
            self.public_ip_address,
            user=self.user,
            connect_kwargs=dict(key_filename=join(expanduser("~"), ".aws/key"))
        )

    def optimise(self):
        """ optimse settings for gpu
        https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/optimize_gpu.html
        """
        if not self.instance_type.startswith(("p2", "p3", "g3")):
            return

        self.sudo("nvidia-smi --auto-boost-default=0", hide="stdout")
        if self.instance_type.startswith("p2"):
            self.sudo("nvidia-smi -ac 2505,875", hide="stdout")
        elif self.instance_type.startswith("p3"):
            self.sudo("nvidia-smi -ac 877,1530", hide="stdout")
        elif self.instance_type.startswith("g3"):
            self.sudo("nvidia-smi -ac 2505,1177", hide="stdout")

    def run(self, *args, **kwargs):
        return self.connection.run(*args, **kwargs)

    def sudo(self, *args, **kwargs):
        return self.connection.sudo(*args, **kwargs)

    def set_ip(self, ip=0):
        """ sets ip address
        :param ip: ipaddress or index of elastic ip """
        if isinstance(ip, int):
            ip = aws.get_ips()[ip]
        if ip is not None:
            aws.client.associate_address(InstanceId=self.id, PublicIp=ip)
            self.refresh()
            self.set_connection()
        copyclip(ip)

    def jupyter(self):
        """ launch jupyter notebook server """
        self.run("./jupyter.sh")
        self.wait_notebook()

    def nb2local(self, src, dst, dryrun=False):
        """ download .ipynb to local machine """

        src = f"/home/ubuntu/{src}"
        dst = f"c:/users/simon/documents/py/{dst}"
        if dryrun:
            log.info(f"{src}==>{dst}")
            return

        r = self.run(f"find {src} -name *.ipynb", hide="stdout")
        nbs = r.stdout.splitlines()
        for nb in nbs:
            if nb.find(".ipynb_checkpoints") >= 0:
                continue
            dstfile = f"{dst}/{nb[len(src) + 1:]}"
            if dryrun:
                log.info(dstfile)
            else:
                os.makedirs(os.path.dirname(dstfile), exist_ok=True)
                self.connection.get(nb, dstfile)


#############################################################################################


def copyclip(text):
    """ copy to clipboard """
    try:
        pyperclip.copy(text)
    except Exception:
        log.warning("pyperclip cannot find copy/paste mechanism")
