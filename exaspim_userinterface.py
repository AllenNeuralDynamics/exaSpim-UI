import napari
from qtpy.QtWidgets import QDockWidget, QTabWidget,QPlainTextEdit, QDialog, QFrame
from PyQt5 import QtWidgets
import exaspim.exaspim as exaspim
from widgets.instrument_parameters import InstrumentParameters
from widgets.volumeteric_acquisition import VolumetericAcquisition
from widgets.livestream import Livestream
from widgets.lasers import Lasers
from widgets.tissue_map import TissueMap
import logging
import traceback
import pyqtgraph.opengl as gl
import io

class UserInterface:

    def __init__(self, config_filepath: str,
                 log_filename: str = 'debug.log',
                 console_output: bool = True,
                 console_output_level: str = 'info',
                 simulated: bool = False):

        try:
            # TODO: Create logger tab at bottom of napari viewer. Also make logger for each class as well
            self.instrument = exaspim.Exaspim(config_filepath=config_filepath, simulated=simulated)
            self.simulated = simulated
            self.cfg = self.instrument.cfg
            self.viewer = napari.Viewer(title='exaSPIM control', ndisplay=2, axis_labels=('x', 'y'))
            self.log = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

            # Set up laser sliders and tabs
            self.laser_widget()

            # Set up automatically generated widget labels and inputs
            instr_params_window = self.instrument_params_widget()

            # Set up main window on gui which combines livestreaming and volumeteric imaging
            main_window = QDockWidget()
            main_window.setWindowTitle('Main')
            main_widgets = {
                'livestream_block': self.livestream_widget(),
                'acquisition_block': self.volumeteric_acquisition_widget(),
            }
            main_window.setWidget(self.vol_acq_params.create_layout(struct='V', **main_widgets))

            # Set up laser window combining laser sliders and selection
            laser_window = QDockWidget()
            laser_widget = {
                #'laser_slider': self.laser_slider,
                'laser_select': self.laser_wl_select,
            }
            laser_window.setWidget(self.laser_parameters.create_layout(struct='H', **laser_widget))

            # Set up tissue map widget
            self.tissue_map_window = self.tissue_map_widget()

            # Add dockwidgets to viewer
            tabbed_widgets = QTabWidget()  # Creating tab object
            tabbed_widgets.setTabPosition(QTabWidget.South)
            tabbed_widgets.addTab(main_window, 'Main Window')  # Adding main window tab
            tabbed_widgets = self.laser_parameters.add_wavelength_tabs(tabbed_widgets)  # Generate laser wl tabs
            tabbed_widgets.addTab(self.tissue_map_window, 'Tissue Map')  # Adding tissue map tab
            self.tissue_map.set_tab_widget(tabbed_widgets)  # Passing in tab widget to tissue map
            self.livestream_parameters.set_tab_widget(tabbed_widgets)  # Passing in tab widget to livestream
            self.vol_acq_params.set_tab_widget(tabbed_widgets)

            self.viewer.window.add_dock_widget(self.livestream_parameters.create_layout(struct='V',
                                                            live=self.livestream_parameters.liveview_widget(),
                                                            tab=tabbed_widgets), name=' ')  # Adding tabs to window
            # TODO: Move set scan to tissue map tab?

            self.viewer.window.add_dock_widget(instr_params_window, name='Instrument Parameters', area='left')
            self.viewer.window.add_dock_widget(laser_window, name="Laser Current", area='bottom')

            self.viewer.scale_bar.visible = True
            self.viewer.scale_bar.unit = "um"
            napari.run()

        finally:
            traceback.print_exc()
            self.close_instrument()
            self.viewer.window.close()

    def instrument_params_widget(self):
        self.instrument_params = InstrumentParameters(self.simulated, self.instrument, self.cfg)
        widgets = {

            'config_properties': self.instrument_params.scan_config(self.cfg),
        }
        instrument_params_widget = self.instrument_params.create_layout('V', **widgets)
        scroll_box = self.instrument_params.scroll_box(instrument_params_widget)
        instrument_params_dock = QDockWidget()
        instrument_params_dock.setWidget(scroll_box)

        return instrument_params_dock

    def livestream_widget(self):

        self.livestream_parameters = Livestream(self.viewer, self.cfg, self.instrument, self.simulated)

        widgets = {
            'grid': self.livestream_parameters.grid_widget(),
            'screenshot': self.livestream_parameters.screenshot_button(),
            'position': self.livestream_parameters.sample_stage_position(),
        }

        # Update config and instrument_params text of change of scan volume
        self.livestream_parameters.set_volume['set_start'].clicked.connect(lambda clicked=None, state='start':
                                                                           self.set_scan_volume(clicked, state))
        self.livestream_parameters.set_volume['set_end'].clicked.connect(lambda clicked=None, state='stop':
                                                                         self.set_scan_volume(clicked, state))
        return self.livestream_parameters.create_layout(struct='V', **widgets)

    def volumeteric_acquisition_widget(self):

        self.vol_acq_params = VolumetericAcquisition(self.viewer, self.cfg, self.instrument, self.simulated)
        widgets = {
            'volumetric_image': self.vol_acq_params.volumeteric_imaging_button(),
            'waveform': self.vol_acq_params.waveform_graph(),
        }

        return self.vol_acq_params.create_layout(struct='V', **widgets)

    def tissue_map_widget(self):

        self.tissue_map = TissueMap(self.instrument)

        widgets = {
            'graph': self.tissue_map.graph(),
            'functions': self.tissue_map.create_layout(struct='H', rotate=self.tissue_map.rotate_buttons(),
                                                                    point=self.tissue_map.mark_graph())
        }
        widgets['functions'].setMaximumHeight(75)
        return self.tissue_map.create_layout(struct='V', **widgets)

    def laser_widget(self):

        self.laser_parameters = Lasers(self.viewer, self.cfg, self.instrument, self.simulated)
        widgets = {
            'splitter': self.laser_parameters.laser_power_splitter(),
            'power': self.laser_parameters.laser_power_slider(),
        }
        self.laser_wl_select = self.laser_parameters.laser_wl_select()
        #self.laser_slider = self.laser_parameters.create_layout(struct='H', **widgets)

    # TODO: Can we calculate new volume in livestream and then when instrument_params_widget is clicked update widgets?
    def set_scan_volume(self, clicked, state):

        """When volume of scan is changed, the config and widgets are subsequently updated"""

        direction = ['X', 'Y', 'Z']
        current = self.livestream_parameters.sample_pos if self.instrument.livestream_enabled.is_set() \
                                                      else self.instrument.sample_pose.get_position()
        set_start = self.instrument.start_pos

        if set_start is None:
            self.livestream_parameters.set_volume['set_end'].setHidden(False)
            self.livestream_parameters.set_volume['clear'].setHidden(False)
            self.instrument.set_scan_start(current)

        else:
            if state == 'start':
                self.instrument.set_scan_start(current)
                if self.livestream_parameters.end_scan == None:
                    return
                else:
                    self.update_volume(direction)

            else:
                self.livestream_parameters.end_scan = current
                self.log.info(f'Scan end position set to {self.livestream_parameters.end_scan["X"]}, '
                              f'{self.livestream_parameters.end_scan["Y"]}, '
                              f'{self.livestream_parameters.end_scan["Z"]}')
                self.update_volume(direction)

    def update_volume(self, directions):
        start = self.instrument.start_pos
        end = self.livestream_parameters.end_scan

        for direction in directions:
            self.log.info(f"Setting volume limits.")
            volume = end[direction] - start[direction]
            if volume < 0:
                self.instrument_params.error_msg('Invalid Volume',
                                                 'Invalid start and end coordinates '
                                                 'resulting in negative volume values.\n'
                                                 f'Start: {start["X"]}, {start["Y"]}, {start["Z"]}\n '
                                                 f'End: {end["X"]}, {end["Y"]}, {end["Z"]}')
                return
            self.cfg.imaging_specs[f'volume_{direction}_um'] = volume * 1 / 10
            self.instrument_params.imaging_specs[f'volume_{direction}_um']. \
                setText(str(volume * 1 / 10))

    def close_instrument(self):
        self.instrument.cfg.save()
        self.instrument.close()
