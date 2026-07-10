from ctorm.cnm import CtormCnmSGenerator
from ctorm.config import CtormPreparedGranule


def test_ctormcnmgenerator():
    test_input: CtormPreparedGranule = {
        "bm": {
            "sds-n-cumulus-prod-nisar-products": "B1",
            "sds-n-cumulus-prod-nisar-jpl-private-data": "B2",
        },
        "g": "NISAR_L0_RRST_VC08_20250821T101036_20250821T101041_P00408_J_001",
        "c": "NISAR_L0A_RRST_BETA_V1",
        "cv": "1",
        "f": [
            {
                "f": "s3://$B1/NISAR_L0A_RRST_BETA_V1/$G/$G.bin",
                "m": "e989430f4c5bfa04eeb26e56f4cd8375",
                "s": 1073829760,
            },
            {
                "f": "s3://$B1/NISAR_L0A_RRST_BETA_V1/$G/$G.rc.yaml",
                "s": 120597,
                "m": "11bcaec780f0d246f3996b3f08680410",
            },
            {
                "f": "s3://$B1/NISAR_L0A_RRST_BETA_V1/$G/$G.bin.qa",
                "s": 1134,
            },
        ],
    }
    ctorm_cnmsgen = CtormCnmSGenerator()
    output = ctorm_cnmsgen(test_input, "FOO")
    assert output
