import logging as log
from . import aws, Resource

class Image(Resource):

	def __init__(self, res):
		self.coll = aws.get_images
		super().__init__(res)


	@classmethod
	def copy(cls, ami, name):
		""" copy ami to your account

		ami: any public ami
		name: name for saved ami
		"""
		from . import Spot, Volume

		# create instance/volume from ami
		instance = Spot(ami)
		volume = Volume(ami)
		instance.terminate(delete_volume=False)

		# save volume with new name
		volume.Name = name
		snapshot = volume.create_snapshot()
		snapshot.register_image()
		volume.delete()

	def set_ena(self):
		""" sets ena on image """
		from . import Instance
		i = Instance(self.Name)
		i.start()
		i.stop(save=True, ena=True)
