# STARPIKE Pixel NTN Replayer

Tools for Pixel 10 measurements that support STARPIKE NTN experiments.

This repository intentionally measures two AP-visible quantities:

- AP cellular CPU overhead on the Android application processor.
- AP-visible cellular activity proxy rates.

**NOTE:** It does not decode modem-internal OTA messages and cannot be interpreted as
MobileInsight-equivalent PHY/MAC/RLC/PDCP/RRC message rates.

## Workflow

1. Run a field phase on the phone.
2. Capture raw evidence into a session directory.
3. Pull sessions to a host.
4. Analyze sessions into CSV summaries.
5. Plot Fig.7-like proxy-rate and CPU-overhead figures.

See [docs/EXPERIMENT.md](docs/EXPERIMENT.md) for setup and details.

See [docs/oneplus_base.md](docs/oneplus_base.md) for getting started.


