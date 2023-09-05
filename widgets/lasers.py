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
        #self.lasers = self.instrument.lasers
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
        print('hello')
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
    #
        """Create slider for every possible laser and hides ones not in use
        :param lasers: dictionary of lasers created """
    #
        laser_power_layout = {}
        for wl in self.possible_wavelengths:  # Convert into strings for convenience. Laser device dict uses int , widget dict uses str
            wls = str(wl)
    #
    #         # Setting commands and initial values for slider widgets. 561 is power based and others current
    #         if wl == 561:
    #             command = Cmd.LaserPower
    #             set_value = float(self.lasers[wl].get(Query.LaserPowerSetting)) if not self.simulated else 15
    #             slider_label = f'{wl}: {set_value}mW'
    #         else:
    #             command = Cmd.LaserCurrent
    #             set_value = float(self.lasers[wl].get(Query.LaserCurrentSetting)) if not self.simulated else 15
    #
            # Creating label and line edit widget
            set_value = 0
            self.laser_power[f'{wls} label'], self.laser_power[wls] = self.create_widget(
                value=None,
                Qtype=QSlider,
                label=f'{wl}: {set_value}mW')
    #
    #         # Setting coloring and bounds for sliders
            self.laser_power[wls].setTickPosition(QSlider.TickPosition.TicksBothSides)
            self.laser_power[wls].setStyleSheet(
                f"QSlider::sub-page:horizontal{{ background-color:{self.cfg.channel_specs[wls]['color']}; }}")
            self.laser_power[wls].setMinimum(0)
            self.laser_power[wls].setMaximum(150)
            self.laser_power[wls].setValue(set_value)
    #
            # Setting activity when slider is moved (update lable value)
            # or released (update laser current or power to slider setpoint)
            # self.laser_power[wls].sliderReleased.connect(
            #     lambda value=self.laser_power[wls].value(), wl=wls, released=True,:
            #     self.laser_power_label(value, wl, released))
            self.laser_power[wls].sliderMoved.connect(
                lambda value=self.laser_power[wls].value(), wl=wls: self.laser_power_label(value, wl))
    #
            # Hides sliders that are not being used in imaging
            if wl not in self.imaging_wavelengths:
                self.laser_power[wls].setHidden(True)
                self.laser_power[f'{wls} label'].setHidden(True)
            laser_power_layout[wls] = self.create_layout(struct='H', label=self.laser_power[f'{wls} label'],
                                                         text=self.laser_power[wls])
    #
        return self.create_layout(struct='V', **laser_power_layout)


    def laser_power_label(self, value, wl: int, released=False, command=None):

        """Set laser current or power to slider set point if released and update label if slider moved
        :param value: value of slider
        :param wl: wavelength of laser
        :param released: if slider was released
        :param command: command to send to laser. Set current or power
        """

        value = self.laser_power[wl].value()
        text = f'{wl}: {value}mW'
        self.laser_power[f'{wl} label'].setText(text)

        # if released:
        #     self.lasers[int(wl)].set(command, float(self.laser_power[wl].value()))
        #     # TODO: When gui talks to hardware, log statement clarifying this
        #     #   Anytime gui changes state of not the gui
            # self.lasers[561].get(Query.LaserPowerSetting)

    # def laser_power_splitter(self):
    #
    #     """
    #     Create slider for laser combiner power split
    #             """
    #
    #     split_percentage = self.lasers['main'].get(Query.PercentageSplitStatus) if not self.simulated else '15%'
    #     self.combiner_power_split['Left label'] = QLabel(f'Left: {100-float(split_percentage[0:-1])}%')  # Left laser is set to 100 - percentage entered
    #
    #     self.combiner_power_split['slider'] = QSlider()
    #     self.combiner_power_split['slider'].setOrientation(QtCore.Qt.Vertical)
    #     self.combiner_power_split['slider'].setMinimum(0)
    #     self.combiner_power_split['slider'].setMaximum(100)
    #     self.combiner_power_split['slider'].setValue(int(split_percentage[0:-1]))
    #     self.combiner_power_split['slider'].sliderReleased.connect(
    #         lambda value=None, released=True, command=Cmd.PercentageSplit:
    #         self.set_power_split(value, released, command))
    #     self.combiner_power_split['slider'].sliderMoved.connect(
    #         lambda value=None: self.set_power_split(value))
    #
    #     self.combiner_power_split['Right label'] = QLabel(
    #         f'Right: {split_percentage[0:-1]}%')  # Right laser is set to percentage entered

        #return self.create_layout(struct='V', **self.combiner_power_split)
    # def set_power_split(self, value, released=False, command=None):
    #
    #     value = int(self.combiner_power_split['slider'].value())
    #     self.combiner_power_split['Right label'].setText(f'Right: {value}%')
    #     self.combiner_power_split['Left label'].setText(f'Left: {100 - int(value)}%')
    #
    #     if released:
    #         self.lasers['main'].set(command, value)
    #         self.log.info(f'Laser power split set. Right: {value}%  Left: {100 - int(value)}%')