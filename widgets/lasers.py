from widgets.widget_base import WidgetBase
from PyQt5.QtCore import Qt, QSize
from qtpy.QtWidgets import QPushButton, QCheckBox, QLabel, QComboBox, QSpinBox, QDockWidget, QSlider, QLineEdit, \
    QTabWidget, QVBoxLayout, QDial
import qtpy.QtCore as QtCore
import logging

class Lasers(WidgetBase):

    def __init__(self, viewer, cfg, instrument, simulated):

        """
            :param viewer: napari viewer
            :param cfg: config object from instrument
            :param instrument: instrument bing used
            :param simulated: if instrument is in simulate mode
        """

        self.viewer = viewer
        self.cfg = cfg
        self.instrument = instrument
        self.simulated = simulated
        self.possible_wavelengths = self.cfg.possible_channels
        self.imaging_wavelengths = self.cfg.channels
        self.log = logging.getLogger(__name__ + "." + self.__class__.__name__)

        self.wavelength_selection = {}
        self.selected = {}
        self.laser_power = {}
        self.tab_map = {}
        self.rl_tab_widgets = {}
        self.combiner_power_split = {}
        self.selected_wl_layout = None
        self.tab_widget = None
        self.dials = {}
        self.dial_widgets = {}

        self.lasers = self.instrument.lasers
        # for wl, specs in self.cfg.channel_specs.items():
        #     laser_class = type('laser', (object,),
        #                        {'get_setpoint': '',
        #                         'set_setpoint': ''})()  # Initialize a laser class
        #     laser_class.get_setpoint = lambda channel = wl: self.cfg.get_channel_ao_voltage(channel)*100
        #     laser_class.set_setpoint = lambda value, channel=wl: self.cfg.set_channel_ao_voltage(channel,
        #                                                                                              value / 100)
        #     self.lasers[wl] = laser_class

    def laser_wl_select(self):

        """Adds a dropdown box with the laser wavelengths that are not selected for the current acquisition based on
        config. Selecting a wavelength adds the wavelength to the lasers to be used during acquisition. To remove a
        wavelength, click on the resultant label"""

        self.wavelength_selection['unselected'] = QComboBox()
        remaining_wavelengths = [str(wavelength) for wavelength in self.possible_wavelengths if
                                 not wavelength in self.imaging_wavelengths]

        remaining_wavelengths.insert(0, '')
        self.wavelength_selection['unselected'].addItems(remaining_wavelengths)
        self.wavelength_selection['unselected'].activated.connect(self.unhide_labels)
        # Adds a 'label' (QPushButton) for every possible wavelength then hides the unselected ones.
        # Pushing labels should hide them and selecting QComboBox should unhide them
        self.wavelength_selection['selected'] = self.selected_wv_label()
        return self.create_layout('V', **self.wavelength_selection)

    def selected_wv_label(self):

        """Adds labels for all possible wavelengths"""
        for wavelengths in self.possible_wavelengths:
            wavelengths = str(wavelengths)
            self.selected[wavelengths] = QPushButton(wavelengths)
            color = self.cfg.channel_specs[wavelengths]
            self.selected[wavelengths].setStyleSheet(f'QPushButton {{ background-color:{color["color"]}; color '
                                                     f':black; }}')
            self.selected[wavelengths].clicked.connect(lambda clicked=None, widget=self.selected[wavelengths]:
                                                       self.hide_labels(clicked, widget))
            if int(wavelengths) not in self.imaging_wavelengths:
                self.selected[wavelengths].setHidden(True)
        self.selected_wl_layout = self.create_layout(struct='V', **self.selected)
        return self.selected_wl_layout

    def hide_labels(self, clicked, widget):

        """Hides laser labels and tabs that are not in use
        :param widget: widget that was clicked to remove from imaging wavelengths
        """

        widget_wavelength = widget.text()
        widget.setHidden(True)
        self.tab_widget.setTabVisible(self.tab_map[widget_wavelength], False)
        self.laser_power[widget_wavelength].setHidden(True)
        self.laser_power[f'{widget_wavelength} label'].setHidden(True)
        self.imaging_wavelengths.remove(int(widget_wavelength))
        self.imaging_wavelengths.sort()
        self.cfg.channels = self.imaging_wavelengths
        self.wavelength_selection['unselected'].addItem(widget.text())

    def unhide_labels(self):

        """Reveals laser labels and tabs that are now in use"""

        index = self.wavelength_selection['unselected'].currentIndex()
        if index != 0:
            widget_wavelength = self.wavelength_selection['unselected'].currentText()
            self.imaging_wavelengths.append(int(widget_wavelength))
            self.imaging_wavelengths.sort()
            self.cfg.channels = self.imaging_wavelengths
            self.wavelength_selection['unselected'].removeItem(index)
            self.selected[widget_wavelength].setHidden(False)
            self.tab_widget.setTabVisible(self.tab_map[widget_wavelength], True)
            self.laser_power[widget_wavelength].setHidden(False)
            self.laser_power[f'{widget_wavelength} label'].setHidden(False)

    def add_wavelength_tabs(self, tab_widget: QTabWidget):

        """Adds laser parameters tabs onto main window for all possible wavelengths
        :param imaging_dock: main window to tabify laser parameter """

        self.tab_widget = tab_widget

        for wl in self.possible_wavelengths:
            wl = str(wl)
            wl_dock = self.scan_wavelength_params(wl)
            scroll_box = self.scroll_box(wl_dock)
            scrollable_dock = QDockWidget()
            scrollable_dock.setWidget(scroll_box)
            self.tab_widget.addTab(scrollable_dock, f'Wavelength {wl}')
            self.tab_map[wl] = self.tab_widget.indexOf(scrollable_dock)
            if int(wl) not in self.imaging_wavelengths:
                tab_widget.setTabVisible(self.tab_map[wl], False)
        return self.tab_widget

    def scan_wavelength_params(self, wv: str):
        """Scans config for relevant laser wavelength parameters
        :param wavelength: the wavelength of the laser"""

        galvo_a = {f'{wv}.galvo.{k}': v for k, v in self.cfg.channel_specs[wv]['galvo_a'].items()}
        galvo_b = {f'{wv}.galvo.{k}': v for k, v in self.cfg.channel_specs[wv]['galvo_b'].items()}
        etl = {f'{wv}.etl.{k}': v for k, v in self.cfg.channel_specs[wv]['etl'].items()}
        dial_values = {**galvo_a,**galvo_b, **etl}

        self.dials[wv] = {}
        self.dial_widgets[wv] = {}
        for k, v in dial_values.items():
            self.dials[wv][k] = QDial()
            self.dials[wv][k].setRange(0, 5000)  # QDials only do int values
            self.dials[wv][k].setNotchesVisible(True)
            self.dials[wv][k].setValue(int(v * 1000))
            self.dials[wv][k].setSingleStep(1)
            self.dials[wv][k].setStyleSheet(
                f"QDial{{ background-color:{self.cfg.channel_specs[str(wv)]['color']}; }}")

            self.dials[wv][k + 'value'] = QLineEdit(str(v))
            self.dials[wv][k + 'value'].setAlignment(QtCore.Qt.AlignCenter)
            self.dials[wv][k + 'value'].setReadOnly(True)
            self.dials[wv][k + 'label'] = QLabel(" ".join(k.split('.')))
            self.dials[wv][k + 'label'].setAlignment(QtCore.Qt.AlignCenter)

            self.dials[wv][k].valueChanged.connect(
                lambda value=str(self.dials[wv][k].value() / 1000),  # Divide to get dec
                       widget=self.dials[wv][k + 'value']: self.update_dial_label(value, widget))
            self.dials[wv][k + 'value'].textChanged.connect(lambda value=self.dials[wv][k].value() / 1000,
                                                                   path=k.split('.'),
                                                                   dict=self.cfg.channel_specs:
                                                            self.config_change(value, path, dict))
            self.dial_widgets[wv][k] = self.create_layout(struct='V', label=self.dials[wv][k + 'label'],
                                                          dial=self.dials[wv][k],
                                                          value=self.dials[wv][k + 'value'])
        return self.create_layout(struct='HV', **self.dial_widgets[wv])

    def update_dial_label(self, value, widget):

        widget.setText(str(value/1000))

    def laser_power_slider(self):

        """Create slider for every possible laser and hides ones not in use
                :param lasers: dictionary of lasers created """

        laser_power_layout = {}

        for wl in self.possible_wavelengths:
            wl = str(wl)

            value = float(self.lasers[wl].get_setpoint()) if not self.simulated else 15
            unit = 'mW'
            min = 0
            max = self.lasers[wl].get_max_setpoint() if not self.simulated else 1000

            # Create slider and label
            self.laser_power[f'{wl} label'], self.laser_power[wl] = self.create_widget(
                value=None,
                Qtype=QSlider,
                label=f'{wl}: {value} {unit}')
            # Set background of slider to laser color, set min, max, and current value
            self.laser_power[wl].setStyleSheet(
                f"QSlider::sub-page:horizontal{{ background-color:{self.cfg.channel_specs[wl]['color']}; }}")
            self.laser_power[wl].setMinimum(min)
            self.laser_power[wl].setMaximum(int(float(max)))
            self.laser_power[wl].setValue(int(float(value)))

            self.laser_power[wl].sliderReleased.connect(
                lambda value=value, unit=unit, wl=wl, released=True:
                self.laser_power_label(value, unit, wl, released))
            self.laser_power[wl].sliderMoved.connect(
                lambda value=value, unit=unit, wl=wl: self.laser_power_label(value, unit, wl))

            # Hides sliders that are not being used in imaging
            if int(wl) not in self.imaging_wavelengths:
                self.laser_power[wl].setHidden(True)
                self.laser_power[f'{wl} label'].setHidden(True)
            laser_power_layout[str(wl)] = self.create_layout(struct='H',
                                                             label=self.laser_power[f'{wl} label'],
                                                             text=self.laser_power[wl])

        return self.create_layout(struct='V', **laser_power_layout)

    def laser_power_label(self, value, unit, wl: int, release=False):

        """Set laser current or power to slider set point if released and update label if slider moved
        :param value: value of slider
        :param wl: wavelength of laser
        :param released: if slider was released
        :param command: command to send to laser. Set current or power
        """

        value = self.laser_power[wl].value()
        text = f'{wl}: {value} {unit}'
        self.laser_power[f'{wl} label'].setText(text)

        if release:
            self.log.info(f'Setting laser {wl} to {value} {unit}')
            self.lasers[wl].set_setpoint(float(round(value)))

