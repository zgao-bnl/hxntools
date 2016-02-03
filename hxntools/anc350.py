import time
from ophyd import (Device, Component as Cpt, FormattedComponent as FC)
from ophyd import (EpicsSignal, EpicsSignalRO, DeviceStatus)
from ophyd.utils import (set_and_wait, TimeoutError)


anc350_dc_controllers = [2, 3, 4, 7]
# add 6 to this list if controller's moved back to the microscope rack
anc350_axis_counts = {1: 6,
                      2: 6,
                      3: 4,
                      4: 6,
                      5: 6,
                      6: 6,
                      7: 3,
                      # 8: 4,
                      }


class Anc350Axis(Device):
    motor = Cpt(EpicsSignal, 'Mtr')
    desc = Cpt(EpicsSignal, 'Mtr.DESC')
    frequency = Cpt(EpicsSignal, 'Freq-SP')
    frequency_rbv = Cpt(EpicsSignal, 'Freq-I')

    amplitude = Cpt(EpicsSignal, 'Ampl-SP')
    amplitude_rbv = Cpt(EpicsSignal, 'Ampl-I')

    def __init__(self, prefix, *, axis_num=None, **kwargs):
        self.axis_num = int(axis_num)
        super(Anc350Axis, self).__init__(prefix, **kwargs)


class Anc350Controller(Device):
    dc_period = Cpt(EpicsSignal, 'DCPer-SP')
    dc_off_time = Cpt(EpicsSignal, 'DCOff-SP')
    dc_enable = Cpt(EpicsSignal, 'DC-Cmd')

    dc_period_rbv = Cpt(EpicsSignalRO, 'DCPer-I')
    dc_off_time_rbv = Cpt(EpicsSignalRO, 'DCOff-I')
    dc_enable_rbv = Cpt(EpicsSignalRO, 'DC-I')

    def __init__(self, prefix, **kwargs):
        super(Anc350Controller, self).__init__(prefix, **kwargs)

    def setup_dc(self, enable, period, off_time, verify=True):
        enable = 1 if enable else 0
        period = int(period)
        off_time = int(off_time)

        self.dc_period.put(period)
        self.dc_off_time.put(off_time)

        if verify:
            _wait_tries(self.dc_period_rbv, period)
            if period != self.dc_period_rbv.get():
                msg = ('Period not set correctly ({} != {})'
                       ''.format(period, self.dc_period_rbv.get()))
                raise RuntimeError('Period not set correctly')

            _wait_tries(self.dc_off_time_rbv, off_time)
            if off_time != self.dc_off_time_rbv.get():
                msg = ('Off time not set correctly ({} != {})'
                       ''.format(off_time, self.dc_off_time_rbv.get()))

                raise RuntimeError(msg)

        self.dc_enable.put(enable)

        if verify:
            _wait_tries(self.dc_enable, enable)
            if enable != self.dc_enable.get():
                msg = ('DC not enabled correctly ({} != {})'
                       ''.format(enable, self.dc_enable_rbv.get()))
                raise RuntimeError(msg)


class HxnAnc350Axis(Anc350Axis):
    def __init__(self, controller, axis_num, **kwargs):
        prefix = 'XF:03IDC-ES{{ANC350:{}-Ax:{}}}'.format(controller, axis_num)
        super().__init__(prefix, axis_num=axis_num, **kwargs)


class HxnAnc350Controller(Anc350Controller):
    def __init__(self, controller, **kwargs):
        prefix = 'XF:03IDC-ES{{ANC350:{}}}'.format(controller)
        super().__init__(prefix, **kwargs)

        self.axes = {axis: HxnAnc350Axis(controller, axis)
                     for axis in range(anc350_axis_counts[controller])}


anc350_controllers = {controller: HxnAnc350Controller(controller)
                      for controller in anc350_axis_counts}


def _dc_status(controller, axis):
    pass


def _wait_tries(signal, value, tries=20, period=0.1):
    '''Wait up to `tries * period` for signal.get() to equal value'''

    while tries > 0:
        tries -= 1
        if signal.get() == value:
            break

        time.sleep(period)


def _dc_toggle(axis, enable, freq, dc_period, off_time):
    print('Axis {} {}: '.format(axis.axis_num, axis.desc.value), end='')
    axis.frequency.put(freq)
    _wait_tries(axis.frequency_rbv, freq)
    print('frequency={}'.format(axis.frequency_rbv.value))


def dc_toggle(enable, controllers=None, freq=100, dc_period=20, off_time=10):
    if controllers is None:
        controllers = anc350_dc_controllers

    for controller in controllers:
        print('Controller {}: '.format(controller), end='')
        controller = anc350_controllers[controller]

        try:
            controller.setup_dc(enable, dc_period, off_time)
        except RuntimeError as ex:
            print('[Failed]', ex)
        except TimeoutError:
            print('Timed out - is the controller powered on?')
            continue
        else:
            if enable:
                print('Enabled duty cycling ({} off/{} on)'.format(
                      controller.dc_off_time_rbv.value,
                      controller.dc_period.value))
            else:
                print('Disabled duty cycling')

        for axis_num, axis in sorted(controller.axes.items()):
            print('\t', end='')
            _dc_toggle(axis, enable, freq, dc_period, off_time)


def dc_on(*, frequency=100):
    dc_toggle(True, freq=frequency)


def dc_off(*, frequency=1000):
    dc_toggle(False, freq=frequency)
