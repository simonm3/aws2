import logging
from . import aws, Resource

log = logging.getLogger(__name__)


class Image(Resource):
    """ aws image resource """

    def __init__(self, res):
        self.coll = aws.get_images
        super().__init__(res)

    @classmethod
    def copy(cls, ami, name):
        """ copy ami to your account
        :param ami: any public ami
        :param name: name for saved ami
        """
        from . import Spot, Volume

        # create instance/volume from ami
        instance = Spot(ami)
        instance.start()
        volume = Volume(ami)
        instance.terminate()

        # save volume with new name
        volume.name = name
        snapshot = volume.create_snapshot()
        snapshot.register_image()
        volume.delete()

    def set_ena(self):
        """ sets ena on image """
        from . import Instance

        i = Instance(self.name)
        i.stop(save=True, ena=True)
