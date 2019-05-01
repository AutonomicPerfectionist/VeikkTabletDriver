#!/usr/bin/env python3
import sys
import libevdev
import datetime
import time


def print_capabilities(l):
    v = l.driver_version
    print("Input driver version is {}.{}.{}".format(v >> 16, (v >> 8) & 0xff, v & 0xff))
    id = l.id
    print("Input device ID: bus {:#x} vendor {:#x} product {:#x} version {:#x}".format(
        id["bustype"],
        id["vendor"],
        id["product"],
        id["version"],
    ))
    print("Input device name: {}".format(l.name))
    print("Supported events:")

    for t, cs in l.evbits.items():
        print("  Event type {} ({})".format(t.value, t.name))

        for c in cs:
            if t in [libevdev.EV_LED, libevdev.EV_SND, libevdev.EV_SW]:
                v = l.value[c]
                print("    Event code {} ({}) state {}".format(c.value, c.name, v))
            else:
                print("    Event code {} ({})".format(c.value, c.name))

            if t == libevdev.EV_ABS:
                a = l.absinfo[c]
                print("       {:10s} {:6d}".format('Value', a.value))
                print("       {:10s} {:6d}".format('Minimum', a.minimum))
                print("       {:10s} {:6d}".format('Maximum', a.maximum))
                print("       {:10s} {:6d}".format('Fuzz', a.fuzz))
                print("       {:10s} {:6d}".format('Flat', a.flat))
                print("       {:10s} {:6d}".format('Resolution', a.resolution))

    print("Properties:")
    for p in l.properties:
        print("  Property type {} ({})".format(p.value, p.name))


def print_event(e):
        print("Event: time {}.{:06d}, ".format(e.sec, e.usec), end='')
        if e.matches(libevdev.EV_SYN):
            if e.matches(libevdev.EV_SYN.SYN_MT_REPORT):
                print("++++++++++++++ {} ++++++++++++".format(e.code.name))
            elif e.matches(libevdev.EV_SYN.SYN_DROPPED):
                print(">>>>>>>>>>>>>> {} >>>>>>>>>>>>".format(e.code.name))
            else:
                print("-------------- {} ------------".format(e.code.name))
        else:
            print("type {:02x} {} code {:03x} {:20s} value {:4d}".format(e.type.value, e.type.name, e.code.value, e.code.name, e.value))


class Tablet():
    def __init__(self, tablet_name):
        self.tablet_name = tablet_name

    def __enter__(self):
        self.dev = libevdev.Device()
        self.dev.name = "Tablet alone"
        ### NB: all the following information needs to be enabled
        ### in order to recognize the device as a tablet.
        # Say that the device will send "absolute" values
        self.dev.enable(libevdev.INPUT_PROP_DIRECT)
        # Say that we are using the pen (not the erasor), and should be set to 1 when we are at proximity to the device.
        # See http://www.infradead.org/~mchehab/kernel_docs_pdf/linux-input.pdf page 9 (=13) and guidelines page 12 (=16), or the https://github.com/linuxwacom/input-wacom/blob/master/4.5/wacom_w8001.c (rdy=proximity)
        self.dev.enable(libevdev.EV_KEY.BTN_TOOL_PEN)
        self.dev.enable(libevdev.EV_KEY.BTN_TOOL_RUBBER)
        # Click
        self.dev.enable(libevdev.EV_KEY.BTN_TOUCH)
        # Press button 1 on pen
        self.dev.enable(libevdev.EV_KEY.BTN_STYLUS)
        # Press button 2 on pen, see great doc
        self.dev.enable(libevdev.EV_KEY.BTN_STYLUS2)
        # Send absolute X coordinate
        self.dev.enable(libevdev.EV_ABS.ABS_X,
                        libevdev.InputAbsInfo(minimum=0, maximum=32767, resolution=100))
        # Send absolute Y coordinate
        self.dev.enable(libevdev.EV_ABS.ABS_Y,
                        libevdev.InputAbsInfo(minimum=0, maximum=32767, resolution=100))
        # Send absolute pressure
        self.dev.enable(libevdev.EV_ABS.ABS_PRESSURE,
                        libevdev.InputAbsInfo(minimum=0, maximum=8191))
        # Use to confirm that we finished to send the informations
        # (to be sent after every burst of information, otherwise
        # the kernel does not proceed the information)
        self.dev.enable(libevdev.EV_SYN.SYN_REPORT)
        # Report buffer overflow
        self.dev.enable(libevdev.EV_SYN.SYN_DROPPED)
        self.uinput = self.dev.create_uinput_device()
        print("New device at {} ({})".format(self.uinput.devnode, self.uinput.syspath))
        # Sleep for a bit so udev, libinput, Xorg, Wayland, ...
        # all have had a chance to see the device and initialize
        # it. Otherwise the event will be sent by the kernel but
        # nothing is ready to listen to the device yet. And it
        # will never be detected in the futur ;-)
        time.sleep(1)
        # self.simulate_first_click()
        self.reset_state()
        return self

    def __exit__(self, type, value, traceback):
        pass

    def reset_state(self):
        self.is_away = True
        self.is_touching = False
        self.pressed_button_1 = False
        self.pressed_button_2 = False
        self.lastmodif = datetime.datetime.now()

    def send_events(self, events, is_away=False):
        self.lastmodif = datetime.datetime.now()
        self.is_away = is_away
        self.uinput.send_events(events)

    def simulate_first_click(self):
        """Useful only the first time to make sure
        xinput detected the input"""
        # Reports that the PEN is close to the surface
        # Important to make sure xinput can detect (and list)
        # the pen. Otherwise, it won't write anything in gimp.
        self.uinput.send_events([
            libevdev.InputEvent(libevdev.EV_KEY.BTN_TOUCH,
                                value=0),
            libevdev.InputEvent(libevdev.EV_KEY.BTN_TOOL_PEN,
                                value=1),
            libevdev.InputEvent(libevdev.EV_SYN.SYN_REPORT,
                                value=0),
        ])
        # Says that the pen it out of range of the tablet. Useful
        # to make sure you can move your mouse, and to avoid
        # strange things during the first draw.
        self.uinput.send_events([
            libevdev.InputEvent(libevdev.EV_KEY.BTN_TOUCH,
                                value=0),
            libevdev.InputEvent(libevdev.EV_KEY.BTN_TOOL_PEN,
                                value=0),
            libevdev.InputEvent(libevdev.EV_SYN.SYN_REPORT,
                                value=0),
        ])


    def send_state_no_pos(self, is_away=False):
        """
        Updates state of virtual tablet device using is_touching, is_away, pressed_button_1 and pressed_button_2
        """
        self.lastmodif = datetime.datetime.now()
        self.is_away = is_away
        print("Away: {}, Touching: {}".format(self.is_away, self.is_touching))
        self.uinput.send_events([
            libevdev.InputEvent(libevdev.EV_KEY.BTN_TOUCH,
                                value=1 if self.is_touching else 0),
            libevdev.InputEvent(libevdev.EV_KEY.BTN_TOOL_PEN,
                                value=1 if not self.is_away else 0),
            libevdev.InputEvent(libevdev.EV_KEY.BTN_STYLUS,
                                value=1 if self.pressed_button_1 else 0),
            libevdev.InputEvent(libevdev.EV_KEY.BTN_STYLUS2,
                                value=1 if self.pressed_button_2 else 0),
            #Syn_report here, I'm leaving it in because I don't know if the input driver sends a syn_report here or not
            libevdev.InputEvent(libevdev.EV_SYN.SYN_REPORT,
                                value=0),
        ])


    def touch_press(self):
        self.is_touching = True
        self.send_state_no_pos()

    def touch_release(self):
        self.is_touching = False
        self.send_state_no_pos()

    def button_1_press(self):
        self.pressed_button_1 = True
        self.send_state_no_pos()

    def button_1_release(self):
        self.pressed_button_1 = False
        self.send_state_no_pos()

    def button_2_press(self):
        self.pressed_button_2 = True
        self.send_state_no_pos()

    def button_2_release(self):
        self.pressed_button_2 = False
        self.send_state_no_pos()

    def move_x(self, abs_x):
        """
        Send ABS_X event on virtual tablet device, with value abs_x
        """
        self.send_events([
            libevdev.InputEvent(libevdev.EV_ABS.ABS_X,
                                value=abs_x),
            #libevdev.InputEvent(libevdev.EV_SYN.SYN_REPORT,
            #                    value=0),
        ])

    def move_y(self, abs_y):
        """
        Send ABS_Y event on virtual tablet device, with value abs_y
        """
        self.send_events([
            libevdev.InputEvent(libevdev.EV_ABS.ABS_Y,
                                value=abs_y),
            #libevdev.InputEvent(libevdev.EV_SYN.SYN_REPORT,
            #                    value=0),
        ])

    def change_pressure(self, pressure):
        """
        Send an ABS_PRESSURE event on the virtual tablet device
        """
        self.send_events([
            libevdev.InputEvent(libevdev.EV_ABS.ABS_PRESSURE,
                                value=pressure),
            #libevdev.InputEvent(libevdev.EV_SYN.SYN_REPORT,
            #                    value=0),
        ])

    def handle_event(self, e):
        """
        Translate input event into virtual device event
        Supported events: ABS_PRESSURE, ABS_X, ABS_Y, BTN_LEFT, SYN_REPORT
        """
        if e.matches(libevdev.EV_ABS.ABS_PRESSURE):
            self.change_pressure(e.value)
        elif e.matches(libevdev.EV_ABS.ABS_X):
            self.move_x(e.value)
        elif e.matches(libevdev.EV_ABS.ABS_Y):
            self.move_y(e.value)
        elif e.matches(libevdev.EV_KEY.BTN_LEFT):
            if e.value == 1:
                self.touch_press()
            else:
                self.touch_release()
        elif e.matches(libevdev.EV_SYN.SYN_REPORT):
            #SYN_REPORT stands for "sync report," should be sent after every update (but not necessarily after every event)
            #Used for separating events into packets of data, of which all events inside occur at the same time
            #Ex. Mouse updates both X and Y, then sends syn_report. Software treats the x and y updates as occuring at the same time
            libevdev.InputEvent(libevdev.EV_SYN.SYN_REPORT,
                                value=0)
        else:
            print("Unkown event:")
            print_event(e)



def main(args):
    path = args[1]
    try:
        with Tablet("Tablet alone") as tablet:
            ### Read the events from real graphics tablet
            with open(path, "rb") as fd:
                l = libevdev.Device(fd)
                print_capabilities(l)
                print("################################\n"
                      "#      Waiting for events      #\n"
                      "################################")
                while True:
                    try:
                        ev = l.events()
                        for e in ev:
                            print_event(e)
                            tablet.handle_event(e)
                    except libevdev.EventsDroppedException:
                        for e in l.sync():
                            print_event(e)
                            tablet.handle_event(e)
    except KeyboardInterrupt:
        pass
    except IOError as e:
        import errno
        if e.errno == errno.EACCES:
            print("Insufficient permissions to access {}".format(path))
        elif e.errno == errno.ENOENT:
            print("Device {} does not exist".format(path))
        else:
            raise e
    except OSError as e:
        print(e)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: sudo {} /dev/input/eventX".format(sys.argv[0]))
        print(" $ sudo evtest")
        print("can help you to know which file to use.")
        sys.exit(1)
    main(sys.argv)
