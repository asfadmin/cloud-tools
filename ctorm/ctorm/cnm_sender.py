from logging import getLogger
from typing import List

from ctorm.cnm import CtormCnmSGenerator
from ctorm.config import CtormConfig, CtormPreparedGranule

log = getLogger(__name__)


class CnmSender:
    def __init__(
        self,
        cfg: CtormConfig,
        granules: List[CtormPreparedGranule],
        provider: str = "TODO: PROVIDER",
    ):
        self.cfg = cfg
        self.granules = granules
        self.provider = provider
        self.cnm_s_generator = CtormCnmSGenerator()

    def send_all(self):
        for granule in self.granules:
            cnms = self.cnm_s_generator(granule, self.provider)
            log.debug("Sending %s", cnms)
