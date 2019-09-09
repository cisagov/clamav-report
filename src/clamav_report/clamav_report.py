#!/usr/bin/env python

"""ClamAV data gathering and report generation tool.

Usage:
  clamav-report [--log-level=LEVEL] [--group=GROUP] <inventory-file> <output-csv-file>
  clamav-report (-h | --help)

Options:
  -g --group=GROUP       Inventory host group to access. [default: all]
  -h --help              Show this message.
  --log-level=LEVEL      If specified, then the log level will be set to
                         the specified value.  Valid values are "debug", "info",
                         "warning", "error", and "critical". [default: info]
"""

from collections import defaultdict
from datetime import datetime
import csv
import dateutil.tz as tz
import logging
import shutil
import sys

from ansible import context
from ansible.executor.task_queue_manager import TaskQueueManager
from ansible.inventory.manager import InventoryManager
from ansible.module_utils.common.collections import ImmutableDict
from ansible.parsing.dataloader import DataLoader
from ansible.playbook.play import Play
from ansible.plugins.callback import CallbackBase
from ansible.vars.manager import VariableManager
import ansible.constants as ANSIBLE_CONST
import docopt

from ._version import __version__

FIELDS = (
    "GROUPNAME",
    "COMPUTER_NAME",
    "IP_ADDR1",
    "OPERATION_SYSTEM",
    "SERVICE_PACK",
    "MAJOR_VERSION",
    "MINOR_VERSION",
    "AGENT_VERSION",
    "CIDS_ENGINE_VERSION",
    "CIDS_DRV_ONOFF",
    "LAST_SCAN_TIME",
    "LAST_VIRUS_TIME",
    "PATTERNDATE",
    "COMPUTER_DOMAIN_NAME",
    "CURRENT_LOGIN_USER",
    "FIREWALL_ONOFF",
    "AGENT_TYPE",
    "IDS_VERSION",
    "CIDS_DEFSET_VERSION",
    "HI_REASONCODE",
    "HI_REASONDESC",
    "STATUS",
    "AVGENGINE_ONOFF",
    "AP_ONOFF",
    "TAMPER_ONOFF",
    "LAST_DOWNLOAD_TIME",
    "PTP_ONOFF",
    "DA_ONOFF",
    "INFECTED",
    "CONTENT_UPDATE",
    "LAST_UPDATED_TIME",
    "HI_STATUS",
    "VERSION",
)
TIME_FORMAT = "%m/%d/%Y %H:%M:%S"
CLAMAV_DB_FILENAME = "/var/lib/clamav/daily.cld"
LAST_SCAN_LOG_FILENAME = "/var/log/clamav/lastscan.log"
LAST_DETECTION_FILENAME = "/var/log/clamav/last_detection"


class ResultCallback(CallbackBase):
    """Task call back class.

    Collects results from the tasks run on each host.
    """

    def __init__(self):
        """Initialize callback and result storage."""
        super(CallbackBase, self).__init__()
        # stored results as hosts: task_name: task_list
        self.results = defaultdict(lambda: defaultdict(list))

    def v2_runner_on_ok(self, result, **kwargs):
        """Store results of a good task run."""
        # store results for retrieval later
        logging.debug(f"Task callback OK: {result._host.name} - {result.task_name}")
        self.results[result._host.name][result.task_name].append(result._result)

    def v2_runner_on_unreachable(self, result):
        """Handle unreachable hosts."""
        logging.warning(
            f"Task callback UNREACHABLE: {result._host.name} - {result.task_name}"
        )

    def v2_runner_on_failed(self, result, *args, **kwargs):
        """Handle failed tasks."""
        logging.error(f"Task callback FAILED: {result._host.name} - {result.task_name}")


def run_ansible(inventory_filename, hosts="all"):
    """Run ansible with the provided inventory file and host group."""
    # Since the API is constructed for CLI it expects certain options to
    # always be set in the context object.
    context.CLIARGS = ImmutableDict(
        connection="ssh",
        module_path=[],
        forks=10,
        become=None,
        become_method="sudo",
        become_user=None,
        check=False,
        diff=False,
        verbosity=0,
    )

    # Initialize required objects.
    # Takes care of finding and reading yaml, json and ini files.
    loader = DataLoader()
    passwords = dict(vault_pass="secret")

    # Instantiate our ResultCallback for handling results as they come in.
    # Ansible expects this to be one of its main display outlets.
    results_callback = ResultCallback()

    # Create inventory, use path to host config file as source or
    # hosts in a comma separated string.
    logging.debug(f"Reading inventory from: {inventory_filename}")
    inventory = InventoryManager(loader=loader, sources=inventory_filename)

    # Variable manager takes care of merging all the different sources to
    # give you a unified view of variables available in each context.
    variable_manager = VariableManager(loader=loader, inventory=inventory)

    # Create data structure that represents our play, including tasks,
    # this is basically what our YAML loader does internally.
    play_source = dict(
        name="Ansible Play",
        hosts=hosts,
        gather_facts="yes",
        tasks=[
            dict(
                action=dict(
                    module="stat", get_checksum=False, path=LAST_SCAN_LOG_FILENAME
                )
            ),
            dict(
                action=dict(
                    module="stat", get_checksum=False, path=LAST_DETECTION_FILENAME
                )
            ),
            dict(
                action=dict(module="stat", get_checksum=False, path=CLAMAV_DB_FILENAME)
            ),
        ],
    )

    # Create play object, playbook objects use .load instead of init or new methods,
    # this will also automatically create the task objects from the
    # info provided in play_source.
    play = Play().load(play_source, variable_manager=variable_manager, loader=loader)

    # Run it - instantiate task queue manager, which takes care of forking
    # and setting up all objects to iterate over host list and tasks.
    tqm = None
    try:
        tqm = TaskQueueManager(
            inventory=inventory,
            variable_manager=variable_manager,
            loader=loader,
            passwords=passwords,
            stdout_callback=results_callback,  # Use our custom callback.
        )
        logging.debug(f"Starting task queue manager.")
        tqm.run(play)
    finally:
        # We always need to cleanup child procs and
        # the structures we use to communicate with them.
        if tqm is not None:
            logging.debug(f"Cleaning up task queue manager.")
            tqm.cleanup()

        # Remove ansible temporary directory
        logging.debug(
            f"Cleaning up temporary file in {ANSIBLE_CONST.DEFAULT_LOCAL_TMP}"
        )
        shutil.rmtree(ANSIBLE_CONST.DEFAULT_LOCAL_TMP, True)

    return results_callback.results


def timestamp_to_string(mod_time):
    """Convert a UTC timestamp to string."""
    t = datetime.fromtimestamp(mod_time)  # assumes localtime
    t = t.replace(tzinfo=tz.tzlocal())
    t = t.astimezone(tz.tzutc())
    return t.strftime(TIME_FORMAT)


def create_host_row(host_results):
    """Create a row of data from a host's results."""
    facts = host_results["Gathering Facts"][0]["ansible_facts"]
    # extract the mtimes from the "stat" module invocations
    mtimes = dict()
    for stat_task in host_results["stat"]:
        path = stat_task["invocation"]["module_args"]["path"]
        mtime = stat_task["stat"].get("mtime", 0)  # 0 if it doesn't exist
        mtimes[path] = timestamp_to_string(mtime)
    row = {key: None for key in FIELDS}
    row["IP_ADDR1"] = facts["ansible_default_ipv4"]["address"]
    row["COMPUTER_NAME"] = facts["ansible_hostname"]
    row["OPERATION_SYSTEM"] = facts["ansible_system"]
    row["MAJOR_VERSION"] = 0
    row["MINOR_VERSION"] = 0
    row["AGENT_VERSION"] = "0.0.0.0"
    row["CIDS_ENGINE_VERSION"] = "0.0.0.0"
    row["CIDS_DRV_ONOFF"] = "ON"
    row["LAST_SCAN_TIME"] = mtimes[LAST_SCAN_LOG_FILENAME]
    row["LAST_VIRUS_TIME"] = mtimes[LAST_DETECTION_FILENAME]
    row["PATTERNDATE"] = mtimes[CLAMAV_DB_FILENAME]
    return row


def write_csv(fields, data, output_filename, delimiter=","):
    """Write a CVS file out."""
    csv_writer = csv.DictWriter(
        open(output_filename, "w"), fields, extrasaction="ignore", delimiter=delimiter
    )
    csv_writer.writeheader()
    for row in data:
        csv_writer.writerow(row)


def main():
    """Gather ClamAV data from hosts and create a CSV file."""
    args = docopt.docopt(__doc__, version=__version__)
    # Set up logging
    log_level = args["--log-level"]
    try:
        logging.basicConfig(
            format="%(asctime)-15s %(levelname)s %(message)s", level=log_level.upper()
        )
    except ValueError:
        logging.critical(
            f'"{log_level}" is not a valid logging level.  Possible values '
            "are debug, info, warning, and error."
        )
        return 1

    logging.info("Gathering ClamAV data from remote servers.")
    results = run_ansible(
        inventory_filename=args["<inventory-file>"], hosts=args["--group"]
    )

    csv_data = []
    for host, host_results in results.items():
        row = create_host_row(host_results)
        csv_data.append(row)

    logging.info("Generating consolidated virus report: " + args["<output-csv-file>"])
    write_csv(FIELDS, csv_data, args["<output-csv-file>"])

    # Stop logging and clean up
    logging.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())