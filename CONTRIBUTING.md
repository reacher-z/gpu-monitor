# Contributing

Thanks for your interest in contributing!

## How to contribute

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Make your changes
4. Test on a machine with NVIDIA GPUs:
   ```bash
   python gpu_monitor.py --once          # check GPU status
   python gpu_monitor.py --test-notify   # verify notification channels
   ```
5. Commit and push
6. Open a pull request

## Guidelines

- Keep it simple — this is a single-file utility
- Use only the Python standard library (no new dependencies)
- Adding a new notification channel? Follow the pattern of `send_slack()` / `send_ntfy()`
- Test with `--once` and `--test-notify` before submitting

## Reporting issues

Open an issue on GitHub with:
- Python version
- GPU model and driver version (`nvidia-smi`)
- Error output or logs
