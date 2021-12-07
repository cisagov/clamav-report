"""ClamAV data gathering and report generation tool.

Usage:
  clamav-report [options] <inventory-file> <output-csv-file>
  clamav-report (-h | --help)

Options:
  -b --become            Become root when executing Ansible tasks.
  -f --forks=COUNT       Number of hosts to process in parallel. [default: 10]
  -g --group=GROUP       Inventory host group to access. [default: all]
  -h --help              Show this message.
  --log-level=LEVEL      If specified, then the log level will be set to
                         the specified value.  Valid values are "debug", "info",
                         "warning", "error", and "critical". [default: info]
"""

# Standard Python Libraries
from collections import defaultdict
import csv
from datetime import datetime
import logging
import os.path
import shutil
import sys
from typing import Any, Dict

# Third-Party Libraries
from ansible import context
import ansible.constants as ANSIBLE_CONST
from ansible.executor.task_queue_manager import TaskQueueManager
from ansible.inventory.manager import InventoryManager
from ansible.module_utils.common.collections import ImmutableDict
from ansible.parsing.dataloader import DataLoader
from ansible.playbook.play import Play
from ansible.plugins.callback import CallbackBase
from ansible.vars.manager import VariableManager
import dateutil.tz as tz
import docopt
from schema import And, Schema, SchemaError, Use

from ._version import __version__

FIELDS = (
    "Group Name",
    "System Name",
    "Last Update Time",
    "Last Scan Time",
    "Host IPS Status (Host IPS)",
)
TIME_FORMAT = "%m/%d/%Y %H:%M"
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
        logging.debug("Task callback OK: %s - %s", result._host.name, result.task_name)
        self.results[result._host.name][result.task_name].append(result._result)

    def v2_runner_on_unreachable(self, result):
        """Handle unreachable hosts."""
        logging.warning(
            "Task callback UNREACHABLE: %s - %s", result._host.name, result.task_name
        )

    def v2_runner_on_failed(self, result, *args, **kwargs):
        """Handle failed tasks."""
        logging.error(
            "Task callback FAILED: %s - %s", result._host.name, result.task_name
        )


def run_ansible(inventory_filename, become=None, hosts="all", forks=10):
    """Run ansible with the provided inventory file and host group."""
    # Since the API is constructed for CLI it expects certain options to
    # always be set in the context object.
    context.CLIARGS = ImmutableDict(
        connection="ssh",
        module_path=[],
        forks=forks,
        become=become,
        become_method="sudo",
        become_user=None,
        check=False,
        diff=False,
        verbosity=0,
    )

    # Initialize required objects.
    # Takes care of finding and reading yaml, json and ini files.
    loader = DataLoader()
    passwords = dict(vault_pass="secret")  # nosec

    # Instantiate our ResultCallback for handling results as they come in.
    # Ansible expects this to be one of its main display outlets.
    results_callback = ResultCallback()

    # Create inventory, use path to host config file as source or
    # hosts in a comma separated string.
    logging.debug("Reading inventory from: %s", inventory_filename)
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
        logging.debug("Starting task queue manager with forks=%d.", forks)
        tqm.run(play)
    finally:
        # We always need to cleanup child procs and
        # the structures we use to communicate with them.
        if tqm is not None:
            logging.debug("Cleaning up task queue manager.")
            tqm.cleanup()

        # Remove ansible temporary directory
        logging.debug(
            "Cleaning up temporary file in %s", ANSIBLE_CONST.DEFAULT_LOCAL_TMP
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
    mtimes = {}
    for stat_task in host_results["stat"]:
        path = stat_task["invocation"]["module_args"]["path"]
        mtime = stat_task["stat"].get("mtime", 0)  # 0 if it doesn't exist
        mtimes[path] = timestamp_to_string(mtime)
    row = {key: None for key in FIELDS}
    row["System Name"] = facts["ansible_hostname"]
    row["Last Update Time"] = mtimes[CLAMAV_DB_FILENAME]
    row["Last Scan Time"] = mtimes[LAST_SCAN_LOG_FILENAME]
    # row["Last Detection Time"] = mtimes[LAST_DETECTION_FILENAME]
    row["Host IPS Status (Host IPS)"] = "ON"
    return row


def write_csv(fields, data, output_filename, delimiter=","):
    """Write a CVS file out."""
    csv_writer = csv.DictWriter(
        open(output_filename, "w"), fields, extrasaction="ignore", delimiter=delimiter
    )
    csv_writer.writeheader()
    for row in data:
        csv_writer.writerow(row)


def main() -> None:
    """Gather ClamAV data from hosts and create a CSV file."""
    args: Dict[str, str] = docopt.docopt(__doc__, version=__version__)
    # Validate and convert arguments as needed
    schema: Schema = Schema(
        {
            "--forks": And(
                Use(int),
                lambda f: f > 0,
                error="The --forks value must be a positive integer value.",
            ),
            "--log-level": And(
                str,
                Use(str.lower),
                lambda n: n in ("debug", "info", "warning", "error", "critical"),
                error="Possible values for --log-level are "
                + "debug, info, warning, error, and critical.",
            ),
            "<inventory-file>": And(
                str,
                And(os.path.exists, error="Inventory file does not exist."),
                And(os.path.isfile, error="Inventory file must be a file."),
            ),
            str: object,  # Don't care about other keys, if any
        }
    )

    try:
        validated_args: Dict[str, Any] = schema.validate(args)
    except SchemaError as err:
        # Exit because one or more of the arguments were invalid
        print(err, file=sys.stderr)
        sys.exit(1)

    # Set up logging
    log_level = validated_args["--log-level"]
    logging.basicConfig(
        format="%(asctime)-15s %(levelname)s %(message)s", level=log_level.upper()
    )

    logging.info("Gathering ClamAV data from remote servers.")
    results = run_ansible(
        inventory_filename=validated_args["<inventory-file>"],
        become=validated_args["--become"],
        hosts=validated_args["--group"],
        forks=validated_args["--forks"],
    )

    csv_data = []
    for host, host_results in results.items():
        row = create_host_row(host_results)
        csv_data.append(row)

    logging.info(
        "Generating consolidated virus report: %s", validated_args["<output-csv-file>"]
    )
    write_csv(FIELDS, csv_data, validated_args["<output-csv-file>"])

    # Stop logging and clean up
    logging.shutdown()
