"""Collection of tests for the run calculation."""
import random

from django.test import TestCase

from account import util
from account.models import InstanceEvent, Run
from account.tests import helper as account_helper
from util.exceptions import NormalizeRunException
from util.tests import helper as util_helper


class AccountUtilCalculateRunsTest(TestCase):
    """Test cases for recalculating runs."""

    def setUp(self):
        """Set up commonly used data for each test."""
        self.account = account_helper.generate_aws_account()

        self.rhel_image = account_helper.generate_aws_image(
            self.account.aws_account_id, rhel_detected=True)

        self.openshift_and_rhel_image = \
            account_helper.generate_aws_image(
                self.account.aws_account_id,
                is_encrypted=False,
                is_windows=False,
                ec2_ami_id=None,
                rhel_detected=True,
                openshift_detected=True,
            )

        self.instance_type = random.choice(tuple(
            util_helper.SOME_EC2_INSTANCE_TYPES.keys()
        ))
        self.instance_info = \
            util_helper.SOME_EC2_INSTANCE_TYPES[self.instance_type]
        self.instance1 = account_helper.generate_aws_instance(
            account=self.account
        )
        self.rhel_instance = account_helper.generate_aws_instance(
            account=self.account, image=self.rhel_image
        )

        # The first pair of power on/off events for rhel_instance
        self.first_power_on = util_helper.utc_dt(2018, 1, 2, 0, 0, 0)
        self.first_power_off = util_helper.utc_dt(2018, 1, 3, 0, 0, 0)
        self.first_power_on_event = \
            account_helper.generate_single_aws_instance_event(
                self.instance1,
                self.first_power_on,
                event_type=InstanceEvent.TYPE.power_on,
                instance_type=self.instance_type
            )
        self.first_power_off_event = \
            account_helper.generate_single_aws_instance_event(
                self.instance1,
                self.first_power_off,
                event_type=InstanceEvent.TYPE.power_off,
                no_instance_type=True
            )

        # The second pair of power on/off events for rhel_instance
        self.second_power_on = util_helper.utc_dt(2018, 1, 5, 0, 0, 0)
        self.second_power_off = util_helper.utc_dt(2018, 1, 7, 0, 0, 0)
        self.second_power_on_event = \
            account_helper.generate_single_aws_instance_event(
                self.instance1,
                self.second_power_on,
                event_type=InstanceEvent.TYPE.power_on,
                instance_type=self.instance_type
            )
        self.second_power_off_event = \
            account_helper.generate_single_aws_instance_event(
                self.instance1,
                self.second_power_off,
                event_type=InstanceEvent.TYPE.power_off,
                no_instance_type=True
            )

    def test_calculate_runs(self):
        """
        Test that the runs are generated correctly from a series of events.

        The initial run is from a single power_on event and has no power_off:
            [ #------------]

        An additional power off event will then be added:
            [ ##           ]
        This should produce a single run with.

        """
        # Single Run from (2, -)
        util.recalculate_runs([self.first_power_on_event])

        runs = list(Run.objects.all())
        self.assertEqual(1, len(runs))
        self.assertEqual(self.first_power_on, runs[0].start_time)
        self.assertIsNone(runs[0].end_time)

        # Single Run from (2, 3)
        util.recalculate_runs(
            [self.first_power_off_event]
        )

        runs = list(Run.objects.all())
        self.assertEqual(1, len(runs))
        self.assertEqual(self.first_power_on, runs[0].start_time)
        self.assertEqual(self.first_power_off, runs[0].end_time)

    def test_calculate_runs_two_power_on(self):
        """
        Test Runs are correct when two power on events are used.

        The start time of the first event is what's used to generate the run.

        """
        # Two power on events, one from (2, -), the other (5,-)
        # should generate a single run from (2,-)
        util.recalculate_runs(
            [self.first_power_on_event,
             self.second_power_on_event]
        )

        runs = list(Run.objects.all())
        self.assertEqual(1, len(runs))

        self.assertEqual(self.first_power_on, runs[0].start_time)
        self.assertIsNone(runs[0].end_time)

    def test_calculate_runs_out_of_order_events(self):
        """
        Test that Runs are calculated correctly when events are out of order.

        Run after first pair of events (2,7):
            [ ######     ]

        Run after adding an intermediate power_on event at (3,):
            [ ######     ]

        Run after adding an intermediate power_off event at (,5):
            [ ## ###     ]

        """
        # Single Run from (2, 7)
        util.recalculate_runs(
            [self.first_power_on_event, self.second_power_off]
        )
        runs = list(Run.objects.all())
        self.assertEqual(1, len(runs))
        self.assertEqual(self.first_power_on, runs[0].start_time)
        self.assertEqual(self.second_power_off, runs[0].end_time)

        # add power_on event starting from (3,)
        util.recalculate_runs([self.second_power_on_event])
        runs = list(Run.objects.all())
        self.assertEqual(1, len(runs))
        self.assertEqual(self.first_power_on, runs[0].start_time)
        self.assertEqual(self.second_power_off, runs[0].end_time)

        # add power_off event that occurred at (,5)
        util.recalculate_runs([self.second_power_off_event])
        runs = list(Run.objects.all())
        self.assertEqual(2, len(runs))

    def test_calculate_runs_multiple_instances(self):
        """
        Test runs generated by separate instances are computed correctly.

        Instance2 Run:
            [####  ##########]

        Instance1 Run:
            [ ######         ]

        """
        instance2 = account_helper.generate_aws_instance(account=self.account)

        instance2_powered_times = [
            (util_helper.utc_dt(2018, 1, 1, 0, 0, 0),
             util_helper.utc_dt(2018, 1, 4, 0, 0, 0)),
            (util_helper.utc_dt(2018, 1, 7, 0, 0, 0),
             util_helper.utc_dt(2018, 1, 16, 0, 0, 0))
        ]

        instance2_events = account_helper.generate_aws_instance_events(
            instance2,
            powered_times=instance2_powered_times
        )
        util.recalculate_runs(
            [self.first_power_on, instance2_events, self.second_power_off]
        )

        instance1_runs = list(Run.objects.filter(instance=self.instance1))
        instance2_runs = list(Run.objects.filter(instance=instance2))

        self.assertEqual(2, len(instance2_runs))
        self.assertEqual(1, len(instance1_runs))

    def test_calculate_runs_normalizes_information(self):
        """
        Test behavior for events without instance_type information.

        Only the initial event has an instance_type associated. Future
        events have no instance type.
        """
        # The initial event sets the instance type.
        initial_event = account_helper.generate_single_aws_instance_event(
            self.instance1,
            self.first_power_on,
            event_type=InstanceEvent.TYPE.power_on,
            instance_type=self.instance_type
        )

        # No instance type in the second power_on event
        no_instance_type_event = \
            account_helper.generate_single_aws_instance_event(
                self.instance1,
                self.second_power_on,
                event_type=InstanceEvent.TYPE.power_on,
                no_instance_type=True
            )

        util.recalculate_runs(
            [initial_event, self.second_power_off_event,
             no_instance_type_event, self.second_power_off]
        )

        runs = list(Run.objects.all())

        self.assertEqual(2, len(runs))

        # Check that memory, vcpu are set correctly on the first run
        self.assertEqual(self.instance_type, runs[0].instance_type)
        self.assertEqual(self.instance_info.memory, runs[0].memory)
        self.assertEqual(self.instance_info.vcpu, runs[0].vcpu)

        # Check that memory, vcpu are set correctly on the second run
        self.assertEqual(self.instance_type, runs[1].instance_type)
        self.assertEqual(self.instance_info.memory, runs[1].memory)
        self.assertEqual(self.instance_info.vcpu, runs[1].vcpu)

    def test_get_cloud_account_overview_type_changes_while_running(self):
        """
        Test when an instance seems to change type while running.

        This should never happen, and if it does, it should raise an exception.
        """
        events = []

        # we specifically want an instance type that has not-1 values for
        # memory and cpu so we can verify different numbers in the results.
        instance_type_1 = 't2.micro'
        instance_type_2 = 't2.large'

        events.append(
            account_helper.generate_single_aws_instance_event(
                self.rhel_instance,
                util_helper.utc_dt(2018, 1, 1, 0, 0, 0),
                InstanceEvent.TYPE.power_on,
                ec2_ami_id=self.rhel_image.ec2_ami_id,
                instance_type=instance_type_1,
            )
        )
        events.append(
            account_helper.generate_single_aws_instance_event(
                self.rhel_instance,
                util_helper.utc_dt(2018, 1, 2, 0, 0, 0),
                InstanceEvent.TYPE.attribute_change,
                instance_type=instance_type_2,
                no_image=True,
                no_subnet=True,
            )
        )
        events.append(
            account_helper.generate_single_aws_instance_event(
                self.rhel_instance,
                util_helper.utc_dt(2018, 1, 3, 0, 0, 0),
                InstanceEvent.TYPE.power_off,
                no_image=True,
                no_instance_type=True,
                no_subnet=True,
            )
        )
        with self.assertRaises(NormalizeRunException):
            util.recalculate_runs(events)

    def test_instanceevent_machineimage_ignored(self):
        """
        Test machineimage source is correct.

        When generating the run we should look at the
        instance.machineimage instead of instanceevent.machineimage.

        """
        # generate event for instance_1 with the rhel/openshift image
        event = account_helper.generate_single_aws_instance_event(
            self.rhel_instance, self.first_power_on,
            InstanceEvent.TYPE.power_on,
            self.openshift_and_rhel_image.ec2_ami_id,
            instance_type=self.instance_type
        )
        util.recalculate_runs(event)
        runs = list(Run.objects.all())
        self.assertEqual(self.rhel_instance, runs[0].image)

    # the following tests are assuming that the events have been returned
    # from the _get_relevant_events() function which will only return events
    # during the specified time period **or** if no events exist during the
    # time period, the last event that occurred. Therefore, the validate method
    # makes sure that we ignore out the off events that occurred before start
    def test_validate_event_off_after_start(self):
        """Test that an off event after start is a valid event to inspect."""
        powered_time = util_helper.utc_dt(2018, 1, 10, 0, 0, 0)

        event = account_helper.generate_single_aws_instance_event(
            self.rhel_instance, powered_time, InstanceEvent.TYPE.power_off
        )
        is_valid = util.validate_event(event, self.first_power_on)
        self.assertEqual(is_valid, True)

    def test_validate_event_on_after_start(self):
        """Test that an on event after start is a valid event to inspect."""
        powered_time = util_helper.utc_dt(2018, 1, 10, 0, 0, 0)

        event = account_helper.generate_single_aws_instance_event(
            self.rhel_instance, powered_time, InstanceEvent.TYPE.power_on
        )
        is_valid = util.validate_event(event, self.first_power_on)
        self.assertEqual(is_valid, True)

    def test_validate_event_on_before_start(self):
        """Test that an on event before start is a valid event to inspect."""
        powered_time = util_helper.utc_dt(2017, 12, 10, 0, 0, 0)

        event = account_helper.generate_single_aws_instance_event(
            self.rhel_instance, powered_time, InstanceEvent.TYPE.power_on
        )
        is_valid = util.validate_event(event, self.first_power_on)
        self.assertEqual(is_valid, True)

    def test_validate_event_off_before_start(self):
        """Test that an off event before start is not a valid event."""
        powered_time = util_helper.utc_dt(2017, 12, 10, 0, 0, 0)

        event = account_helper.generate_single_aws_instance_event(
            self.rhel_instance, powered_time, InstanceEvent.TYPE.power_off
        )
        is_valid = util.validate_event(event, self.first_power_on)
        self.assertEqual(is_valid, False)
