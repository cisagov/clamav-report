# clamav-report 🦪📊 #

[![GitHub Build Status](https://github.com/cisagov/clamav-report/workflows/build/badge.svg)](https://github.com/cisagov/clamav-report/actions)
[![Coverage Status](https://coveralls.io/repos/github/cisagov/clamav-report/badge.svg?branch=develop)](https://coveralls.io/github/cisagov/clamav-report?branch=develop)
[![Total alerts](https://img.shields.io/lgtm/alerts/g/cisagov/clamav-report.svg?logo=lgtm&logoWidth=18)](https://lgtm.com/projects/g/cisagov/clamav-report/alerts/)
[![Language grade: Python](https://img.shields.io/lgtm/grade/python/g/cisagov/clamav-report.svg?logo=lgtm&logoWidth=18)](https://lgtm.com/projects/g/cisagov/clamav-report/context:python)
[![Known Vulnerabilities](https://snyk.io/test/github/cisagov/clamav-report/develop/badge.svg)](https://snyk.io/test/github/cisagov/clamav-report)

This is a tool that will collect ClamAV data using an
[Ansible](https://www.ansible.com) inventory and create a CSV file
that is able to be ingested by legacy compliance tools.

It assumes that ClamAV has been installed using the
[Ansible ClamAV role](https://github.com/cisagov/ansible-role-clamav).

## Usage ##

```console
$ clamav-report tests/files/inventory.txt clamav-201909.csv

2019-09-09 15:39:41,256 INFO Gathering ClamAV data from remote servers.
2019-09-09 15:39:42,292 WARNING Task callback UNREACHABLE: borked.foo.gov - Gathering Facts
2019-09-09 15:39:47,268 INFO Generating consolidated virus report: clamav-201909.csv
```

## Contributing ##

We welcome contributions!  Please see [`CONTRIBUTING.md`](CONTRIBUTING.md) for
details.

## License ##

This project is in the worldwide [public domain](LICENSE).

This project is in the public domain within the United States, and
copyright and related rights in the work worldwide are waived through
the [CC0 1.0 Universal public domain
dedication](https://creativecommons.org/publicdomain/zero/1.0/).

All contributions to this project will be released under the CC0
dedication. By submitting a pull request, you are agreeing to comply
with this waiver of copyright interest.
