import logging
import uuid
from . import aws, Resource

log = logging.getLogger(__name__)


class Snapshot(Resource):
    """ an AWS snapshot resource """

    def __init__(self, res):
        self.coll = aws.get_snapshots
        super().__init__(res)

    def register_image(self, name=None):
        """ blocking save
        
        :param name: saved image name
        """
        from . import Image

        if not name:
            name = self.name

        # set delete_on_terminaton=False and hvm
        bdm = dict(
            DeviceName="/dev/xvda",
            Ebs=dict(DeleteOnTermination=False, SnapshotId=self.id, VolumeType="gp2"),
        )
        imageid = aws.client.register_image(
            Architecture="x86_64",
            Name=str(uuid.uuid4()),
            BlockDeviceMappings=[bdm],
            RootDeviceName="/dev/xvda",
            VirtualizationType="hvm",
        )["ImageId"]
        image = Image(aws.ec2.Image(imageid))

        # wait for save complete
        waiter = aws.client.get_waiter("image_available")
        log.info(f"saving image")
        waiter.wait(ImageIds=[image.id])
        image.name = name

        # deregister all except latest
        images = aws.get_images(name=name)
        for image in images[:-1]:
            aws.client.deregister_image(ImageId=image.id)

    ####### rarely used. NOT FULLY TESTED #####################################

    def attach(self, instance):
        """ create a volume and attach """
        from . import Volume

        if isinstance(instance, str):
            instance = aws.get_instances(name=instance)[-1]

        r = aws.client.create_volume(
            SnapshotId=self.id,
            AvailabilityZone=instance.placement["AvailabilityZone"],
            VolumeType="gp2",
        )
        volume = Volume(aws.ec2.Volume(r["VolumeId"]))
        volume.name = self.name
        volume.attach(instance)
