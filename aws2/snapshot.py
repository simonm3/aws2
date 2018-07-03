import logging as log

import uuid
from . import aws, Resource


class Snapshot(Resource):

    def __init__(self, res):
        self.coll = aws.get_snapshots
        super().__init__(res)

    def register_image(self, name=None):
        """ blocking save
        
        name: saved image name
        """
        from . import Image
        
        if not name:
            name = self.Name

        # set delete_on_terminaton=False and hvm
        bdm = dict(DeviceName="/dev/xvda",
                   Ebs=dict(DeleteOnTermination=False,
                            SnapshotId=self.id,
                            VolumeType="gp2"))
        imageid = aws.client.register_image(
            Architecture='x86_64',
            Name=str(uuid.uuid4()),
            BlockDeviceMappings=[bdm],
            RootDeviceName="/dev/xvda",
            VirtualizationType="hvm")["ImageId"]
        image = Image(aws.ec2.Image(imageid))

        # wait for save complete
        waiter = aws.client.get_waiter("image_available")
        log.info(f"waiting for image to be saved")
        waiter.wait(ImageIds=[image.id])
        image.Name = name

        # deregister all except latest
        images = aws.get_images(Name=name)
        for image in images[:-1]:
            aws.client.deregister_image(ImageId=image.id)

    ####### rarely used. NOT FULLY TESTED #####################################

    def attach(self, instance):
        """ create a volume and attach """
        from . import Volume

        if isinstance(instance, str):
            instance = aws.get_instances(Name=instance)[-1]

        r = aws.client.create_volume(
            SnapshotId=self.id,
            AvailabilityZone=instance.placement["AvailabilityZone"],
            VolumeType="gp2")
        volume = Volume(aws.ec2.Volume(r["VolumeId"]))
        volume.Name = self.Name
        volume.attach(instance)
