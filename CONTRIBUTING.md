# Contributing to pimify

First off, thanks for taking the time to contribute! ❤️

## How to Contribute
We welcome contributions in various forms, including bug reports, feature requests, code improvements, documentation enhancements, and more. Here's how you can contribute:

1. `Opening Issues`: If you encounter any bugs, have suggestions, or want to request a new feature, please open an issue on our tracker[https://github.com/users/suriya-mca/projects/14/views/1].
2. `Submitting Pull Requests (PRs)`: We encourage you to fork this repository, make your changes, and submit a pull request. Please ensure your PR adheres to the following guidelines:
- Describe the problem or feature in the PR description
- Follow the existing coding style and conventions
- Include relevant tests if applicable
- Update the documentation, if necessary
- Ensure your changes don't introduce any breaking changes unless absolutely necessary

## Development Workflow
This project follows the Git branching model with two main branches:

- main: This branch is for production-ready code. It should always contain stable and tested code
- dev: This branch is for ongoing development. Features and fixes are developed here before being merged into main

## Getting Started
To start contributing, follow these steps:

- Fork this repository to your GitHub account
- Clone the forked repository to your local machine
- Create your Feature or Fix Branch (`git checkout -b feature/your-change`)
- Make your changes and ensure they are properly tested
- Commit your Changes (`git commit -m 'Describe your change'`)
- Push to the Branch (`git push origin feature/your-change`)
- Open a Pull Request

## Run the checks

CI (`.github/workflows/ci.yml`) runs these four commands on every push and PR to `dev`/`main`. Run them locally before pushing — a red pipeline is almost always one of these:

```bash
uv sync --locked
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run
uv run python manage.py test --noinput
```

## License
By contributing to pimify, you agree that your contributions will be licensed under the Apache License 2.0 (see `LICENSE`).
