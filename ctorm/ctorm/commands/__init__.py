import argparse
import logging

from ctorm.config import CtormConfig
from ctorm.prepare import CtormPrepare

log = logging.getLogger(__name__)


def cmd_prepare(args: argparse.Namespace):
    cfg = CtormConfig.from_file(
        cfg_file=args.cfg_file,
    )
    prepare = CtormPrepare(cfg)
    prepare.prepare()


def cmd_cnm_sender(args: argparse.Namespace):
    # TODO: something like:
    #
    # from ctorm.cnm_sender import CnmSender
    #
    # cfg = CtormConfig.from_file(cfg_file=args.cfg_file)
    # cnm_sender = CnmSender(cfg)
    # cnm_sender.run(max_messages=args.max_messages)
    #
    raise NotImplementedError("cnm_sender command is not implemented yet")
