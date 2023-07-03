import logging
from organize_pictures import OrganizePictures


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter('[ %(asctime)s ][ %(levelname)s ] %(message)s')

fh = logging.FileHandler(f"{__name__}.log")
fh.setLevel(logging.DEBUG)
fh.setFormatter(formatter)

ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
ch.setFormatter(formatter)

logger.addHandler(fh)
logger.addHandler(ch)


organizer = OrganizePictures(logger=logger, source_directory="./pics", destination_directory="./renamed")

organizer.run()
