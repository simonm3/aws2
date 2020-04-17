from .resource import Resource
from .instance import Instance
from .image import Image
from .snapshot import Snapshot
from .volume import Volume
from .spot import Spot
from . import aws

import logging
log = logging.getLogger(__name__)