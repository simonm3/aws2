import logging as log

import fabric.api as fab
from . import aws, Resource


class Volume(Resource):

    def __init__(self, res):
        self.coll = aws.get_volumes
        super().__init__(res)

    def create_snapshot(self, name=None):
        """ blocking save """
        from . import Snapshot
        
        if name is None:
            name = self.Name

        # create
        snapshot = Snapshot(self.res.create_snapshot())
        waiter = aws.client.get_waiter("snapshot_completed")
        waiter.config.max_attempts = 99999
        log.info(f"waiting for snapshot")
        waiter.wait(SnapshotIds=[snapshot.id])

        # after created
        snapshot.Name = name
        snapcount = len(aws.get_snapshots(Name=name))
        log.info(f"You now have {snapcount} {name} snapshots")
        return snapshot

    def delete(self):
        """ release name and delete
        """
        self.Name = ""
        waiter = aws.client.get_waiter("volume_available")
        log.info(f"waiting for volume available")
        waiter.wait(VolumeIds=[self.id])
        self.res.delete()

    def create_image(self, name=None):
        """ save as snapshot and create image """
        if name is None:
            name = self.Name
        snapshot = self.create_snapshot(name)
        snapshot.register_image()

    ####### rarely used. NOT FULLY TESTED #####################################

    def attach(self, instance):
        """ attach to instance
        instance: instance object or instance name
        """
        from . import Instance
        
        instance = Instance(instance)
        self.detach()
        instance.attach_volume(VolumeId=self.id, Device='/dev/xvdf')
        self.mount()
        log.info("volume attached and mounted")

    def mount(self, device="/dev/xvdf", mountpoint="/v1"):
        """ mount volume """
        fab.sudo(f"mkdir -p {mountpoint}")
        with fab.quiet():
            r = fab.sudo(f"mount {device} {mountpoint}")
            if r.failed:
                # bootable snapshot has single partition
                device = device+"1"
                fab.sudo(f"mount {device} {mountpoint}")
        log.info("mounted volume")

    def formatdisk(self, device="/dev/xvdf"):
        """ format volume if no file system """
        with fab.quiet():
            r = fab.sudo(f"blkid {device}")
        if r.succeeded:
            log.warning("volume is already formatted")
            return
        r = fab.sudo(f"mkfs -t ext4 {device}")
        if r.failed:
            raise Exception("format failed as no volume attached")
        log.info("volume formatted")

    def resize(self, size, mountpoint="/dev/xvdf"):
        """ make volume larger. Note smaller is not allowed. """
        aws.client.modify_volume(VolumeId=self.id, size=size)
        fab.sudo(f"resize2fs {mountpoint}")


    def unmount(self, mountpoint="/v1"):
        """ unmount using force if required """
        with fab.quiet():
            r = fab.sudo(f"umount {mountpoint}")
            if r.succeeded:
                log.info("volume dismounted")
            else:
                log.warning("dismount failed. trying to force.")
                r = fab.sudo(f"fuser -km {mountpoint}")
                if r.succeeded:
                    log.info("volume dismounted")
                else:
                    log.warning("failed to force dismount")

    def detach(self, **kwargs):
        """ blocking detach """
        if not self.attachments:
            return
        self.detach_from_instance(InstanceId=self.attachments[
            0]["InstanceId"], **kwargs)
        waiter = aws.client.get_waiter("volume_available")
        log.info(f"waiting for volume available")
        waiter.wait(VolumeIds=[self.id])