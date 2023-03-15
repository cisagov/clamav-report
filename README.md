# clamav-report 🦪📊 #

[![GitHub Build Status](https://github.com/cisagov/clamav-report/workflows/build/badge.svg)](https://github.com/cisagov/clamav-report/actions)
[![CodeQL](https://github.com/cisagov/clamav-report/workflows/CodeQL/badge.svg)](https://github.com/cisagov/clamav-report/actions/workflows/codeql-analysis.yml)
[![Coverage Status](https://coveralls.io/repos/github/cisagov/clamav-report/badge.svg?branch=develop)](https://coveralls.io/github/cisagov/clamav-report?branch=develop)
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

For gathering ClamAV log data from AWS instances that are accessible via
[SSM](https://docs.aws.amazon.com/systems-manager/latest/userguide/what-is-systems-manager.html),
the `clamav_log_report.sh` shell script has been provided in the `extras`
directory:

```console
$ ./extras/clamav_log_report.sh i-0123456789abcdef0

Starting session with SessionId: iam.username-0123456789abcdef0

bar.foo.gov
----------- SCAN SUMMARY -----------
Known viruses: 8654853
Engine version: 0.103.6
Scanned directories: 5141
Scanned files: 42629
Infected files: 0
Data scanned: 2949.27 MB
Data read: 3249.70 MB (ratio 0.91:1)
Time: 574.106 sec (9 m 34 s)
Start Date: 2023:03:05 06:47:01
End Date:   2023:03:05 06:56:35

Exiting session with sessionId: david.redmin-0123456789abcdef0.
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
