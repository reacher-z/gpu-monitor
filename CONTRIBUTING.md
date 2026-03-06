# Contributing

Thanks for your interest in contributing!

## How to contribute

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Make your changes
4. Test on a machine with NVIDIA GPUs (`python gpu_monitor.py --once`)
5. Commit and push
6. Open a pull request

## Guidelines

- Keep it simple — this is a single-file utility
- Use only the Python standard library (no new dependencies)
- Test with `python gpu_monitor.py --once` before submitting

## Reporting issues

Open an issue on GitHub with:
- Python version
- GPU model and driver version (`nvidia-smi`)
- Error output or logs
