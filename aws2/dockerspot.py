import logging as log

import fabric.api as fab
import pandas as pd

from io import BytesIO
import json
import os
from . import aws, Volume, Spot


class Dockerspot(Spot):
    """ persistent spot instances using docker container on attached volume """

    def __init__(self):
        raise Exception("Dockerspot has not been tested.")


    def start(self, instance_type="p2.xlarge", new=False, size=10):
        """ start spot with attached docker volume
        block until ssh available

        new: True to create new volume
        size: if new then size of volume

        requirements:
            AMI with tag:Name="base". ubuntu, docker, nvidia_docker2, cuda8
            formatted volume saved as snapshot with tag:Name=name
        """
        # define image and volume
        imageId = aws.get_images(Name="base")[-1].id
        if new:
            bdm = [dict(DeviceName="/dev/xvdf",
                        Ebs=dict(DeleteOnTermination=False,
                                 VolumeType="gp2",
                                 VolumeSize=size))]
        else:
            snapshotId = aws.get_snapshots(Name=self.Name)[-1].id
            bdm = [dict(DeviceName="/dev/xvdf",
                        Ebs=dict(DeleteOnTermination=False,
                                 VolumeType="gp2",
                                 SnapshotId=snapshotId))]

        # get cheapest zone
        prices = aws.client.describe_spot_price_history(
            InstanceTypes=[instance_type],
            ProductDescriptions=["Linux/UNIX"])["SpotPriceHistory"]
        prices = pd.DataFrame(prices)
        cheapest = prices.drop_duplicates("AvailabilityZone").iloc[0]
        log.info(f"requesting spot {instance_type} at "
                 f"{float(cheapest.SpotPrice):.2f} in "
                 f"{cheapest.AvailabilityZone}")

        # launch
        spec = dict(
            ImageId=imageId,
            InstanceType=instance_type,
            SecurityGroups=["simon"],
            KeyName="key",
            BlockDeviceMappings=bdm,
            Placement=dict(AvailabilityZone=cheapest.AvailabilityZone))
        self.get_spot(spec)

        # post-launch
        if new:
            volume = list(self.volumes.all())[0]
            volume.format_disk()
            log.warning(
                "new volume so need to manually pull and run container")
        self.set_docker_folder("/v1")

        log.info("setup complete")

    def stop(self, save=True):
        """ terminate instance and save volume as snapshot
        block until snapshot complete
        """
        volume = Volume(self.Name)

        # terminate instance. can release name immediately.
        self.Name = ""
        self.terminate()
        log.info("terminating instance")
        self.wait_until_terminated()
        log.info("instance terminated")

        # save
        if save:
            volume.save()
            # release name after save completed
            volume.Name = ""
        volume.delete()

    def set_docker_folder(self, folder="/var/lib"):
        """ set location of docker images and containers
        folder: /v1=attached volume. /var/lib=default
        """
        # read config
        fname = "/etc/docker/daemon.json"
        config = BytesIO()
        with fab.quiet():
            r = fab.get(fname, config, use_sudo=True)
            if r.succeeded:
                config = json.loads(config.getvalue())
            else:
                config = dict()

        # change config and write back
        config["graph"] = f"{folder}/docker"
        fab.sudo(f"mkdir -p {os.path.dirname(fname)}")
        config = bytes(json.dumps(config), "utf8")
        fab.put(BytesIO(config), fname, use_sudo=True)

        # restart to activate new target folder
        with fab.quiet():
            fab.sudo("service docker restart")
