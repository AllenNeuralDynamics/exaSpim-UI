from widgets.widget_base import WidgetBase
from qtpy.QtWidgets import QLineEdit, QVBoxLayout, QWidget, \
    QHBoxLayout, QLabel, QDoubleSpinBox, QComboBox, QComboBox, QDial, QToolButton, QRadioButton
from qtpy.QtGui import QIntValidator
from tigerasi.device_codes import JoystickInput
from qtpy.QtGui import QPixmap, QImage
import qtpy.QtCore as QtCore
import numpy as np
import cv2

def get_dict_attr(class_def, attr):
    # for obj in [obj] + obj.__class__.mro():
    for obj in [class_def] + class_def.__class__.mro():
        if attr in obj.__dict__:
            return obj.__dict__[attr]
    raise AttributeError


class InstrumentParameters(WidgetBase):

    def __init__(self, simulated, instrument, config):

        self.simulated = simulated
        self.instrument = instrument
        self.cfg = config
        self.column_pixels = self.cfg.sensor_column_count
        self.slit_width = {}
        self.exposure_time = {}
        self.imaging_specs = {}     # dictionary to store attribute labels and input box


    def scan_config(self, config: object, x_game_mode: bool = False):

        """Scans config and finds property types with setter and getter attributes
        :param config: config object from the instrument class"""

        imaging_specs_widgets = {}  # dictionary that holds layout of attribute labels/input pairs

        if not x_game_mode:
            reduced_param = ['ext_storage_dir', 'immersion_medium', 'local_storage_dir',
                                   'subject_id', 'tile_prefix', 'volume_x_um', 'volume_y_um',
                                   'volume_z_um']
            directory = [i for i in dir(config) if i in reduced_param]
        else:
            cpx_attributes = ['exposure_time_s', 'slit_width_pix', 'line_time_us', 'scan_direction']
            directory = [i for i in dir(config) if i not in cpx_attributes]

        for attr in directory:
            value = getattr(config, attr)
            if isinstance(value, list):
                continue
            elif isinstance(getattr(type(config), attr, None), property):
                prop_obj = get_dict_attr(config, attr)

                if prop_obj.fset is not None and prop_obj.fget is not None:

                    self.imaging_specs[attr, '_label'], self.imaging_specs[attr] = \
                        self.create_widget(getattr(config, attr), QLineEdit, label=attr)

                    if attr != 'image_dtype':   # TODO: Hard coded for now but maybe not in the future
                        self.imaging_specs[attr].editingFinished.connect \
                            (lambda obj=config, var=attr, widget=self.imaging_specs[attr]:
                             self.set_attribute(obj, var, widget))
                    else:
                        self.imaging_specs[attr].setReadOnly(True)

                    self.imaging_specs[attr].setToolTip(prop_obj.__doc__)

                    imaging_specs_widgets[attr] = self.create_layout(struct='H',
                                                                     label=self.imaging_specs[attr, '_label'],
                                                                     text=self.imaging_specs[attr])
        return self.create_layout(struct='V', **imaging_specs_widgets)



    def joystick_remap_tab(self):

        """Tab to remap joystick"""


        tiger_axes = [k for k,v in self.instrument.tigerbox.get_joystick_axis_mapping().items() if v == JoystickInput.NONE]
        tiger_axes.append('NONE')

        joystick_mapping = self.instrument.tigerbox.get_joystick_axis_mapping()
        self.joystick_axes = {'JOYSTICK_X':'', 'JOYSTICK_Y':'', 'Z_WHEEL':'', 'F_WHEEL':''}

        self.axis_combobox = {}
        combobox_layout = {}
        for axis in self.joystick_axes.keys():
            self.axis_combobox[axis] = QComboBox()
            self.axis_combobox[axis].addItems(tiger_axes)
            if JoystickInput[axis] in joystick_mapping.values():
                current_text = list(joystick_mapping.keys())[list(joystick_mapping.values()).index(JoystickInput[axis])]
                self.axis_combobox[axis].addItem(current_text)
            else:
                current_text = 'NONE'
            self.joystick_axes[axis] = current_text
            self.axis_combobox[axis].setCurrentText(current_text)
            label = QLabel(f'{axis}:')
            combobox_layout[axis] = self.create_layout(struct='H',
                                                       label=label,
                                                       combobox=self.axis_combobox[axis])
            self.axis_combobox[axis].currentTextChanged.connect(lambda index = None,
                                                                           axis = axis
                                                                    : self.change_joystick_mapping(index, axis))

        left = QToolButton()
        left.setArrowType(QtCore.Qt.ArrowType.LeftArrow)
        right = QToolButton()
        right.setArrowType(QtCore.Qt.ArrowType.RightArrow)
        right_left = self.create_layout(struct='H',
                                        left=left,
                                        right=right,
                                        box=combobox_layout['JOYSTICK_X'])

        up = QToolButton()
        up.setArrowType(QtCore.Qt.ArrowType.UpArrow)
        down = QToolButton()
        down.setArrowType(QtCore.Qt.ArrowType.DownArrow)
        up_down = self.create_layout(struct='H', up=up,
                                     down=down,
                                     box=combobox_layout['JOYSTICK_Y'])

        left_dial = self.create_layout(struct='H', dial=QDial(),
                                       box=combobox_layout['Z_WHEEL'])
        right_dial = self.create_layout(struct='H', dial=QDial(),
                                        box=combobox_layout['F_WHEEL'])

        all = self.create_layout(struct='V', ud=up_down, rl=right_left, ldial=left_dial, rdial=right_dial)
        all.children()[0].addStretch()
        all.children()[0].addSpacing(0)
        all.children()[0].setAlignment(QtCore.Qt.AlignLeft)
        return all

    def change_joystick_mapping(self, index, joystick_axis):

        stage_ax = self.axis_combobox[joystick_axis].currentText()
        if stage_ax == 'NONE':
            # Unmap previous coordinate and add coordinate to all comboboxes
            self.instrument.tigerbox.bind_axis_to_joystick_input(**{self.joystick_axes[joystick_axis]: JoystickInput.NONE})
            for joystick, box in self.axis_combobox.items():
                if joystick == joystick_axis:
                    continue # don't add duplicate of axis
                box.blockSignals(True)
                box.addItem(self.joystick_axes[joystick_axis])
                box.blockSignals(False)
        elif self.joystick_axes[joystick_axis] == 'NONE':
            # Map new stage axis to joystick
            self.instrument.tigerbox.bind_axis_to_joystick_input(
                **{stage_ax: JoystickInput[joystick_axis]})
            for joystick, box in self.axis_combobox.items():
                if joystick == joystick_axis:
                    continue  # don't add duplicate of axis
                box.blockSignals(True)
                box.removeItem(box.findText(stage_ax))
                box.blockSignals(False)
        else:       # Neither stageax or joystick is none
            #Set previous stage axis to map to none and set new axis to joystick axis
            self.instrument.tigerbox.bind_axis_to_joystick_input(**{self.joystick_axes[joystick_axis]:JoystickInput.NONE,
                                                                        stage_ax:JoystickInput[joystick_axis]})
            for joystick, box in self.axis_combobox.items():
                if joystick == joystick_axis:
                    continue  # don't add duplicate of axis
                box.blockSignals(True)
                box.removeItem(box.findText(stage_ax))
                box.addItem(self.joystick_axes[joystick_axis])
                box.blockSignals(False)
        # Update joystick axis
        self.joystick_axes[joystick_axis] = stage_ax

    def brain_orientation_widget(self):

        """Widget to set brain orientation"""
        # Clear brain orientation from last run
        self.cfg.x_anatomical_direction = ''
        self.cfg.y_anatomical_direction = ''
        self.cfg.z_anatomical_direction = ''

        orientation = ['right', 'left', 'flip right', 'flip left']
        self.orientaion_widget = {}

        for pos in orientation:
            img = cv2.imread(r'C:\Users\micah.woodard\PycharmProjects\exaSpim-UI\mid-sagittal-brain.png')
            label = {'x':'Posterior_to_anterior',
                     'y': 'Inferior_to_superior',
                     'z': 'Right_to_left'}
            if 'flip' in pos:
                img = cv2.flip(img, 0)
                label['y'] = 'Superior_to_inferior'
            if 'right' in pos:
                img = cv2.flip(img, 1)
                label['x'] = 'Anterior_to_posterior'
            if pos != 'left' and pos != 'flip right':
                label['z'] = 'Left_to_right'

            pixmap = QImage(img, img.shape[1], img.shape[0], QImage.Format_BGR888)
            img_widget = QLabel()
            img_widget.setPixmap(QPixmap(pixmap.scaled(150, 150, QtCore.Qt.KeepAspectRatio)))
            set_button = QRadioButton()
            set_button.toggled.connect(lambda state = 2, orientations = label, key = pos:
                                       self.set_brain_orientation(state, orientations, key))
            self.orientaion_widget[pos] = self.create_layout("V", image =img_widget, box =set_button)

        img_widget = QLabel('Not Applicable')
        set_button = QRadioButton()
        set_button.toggled.connect(lambda state=2, orientations={k:'N/A' for k in label.keys()}, key='NA':
                                   self.set_brain_orientation(state, orientations, key))
        NA_widget = self.create_layout('V', label=img_widget, button=set_button)
        orientation_widget = self.create_layout('V', top=self.create_layout('VH', **self.orientaion_widget), bottom=NA_widget)
        self.orientaion_widget['NA'] = NA_widget # Retroactivily add NA widget to orientation widget to have correct formatting
        return orientation_widget

    def set_brain_orientation(self, state, orientations: dict, key):

        """Function to set brain orientation in config"""

        # State is 2 if checkmark is pressed
        if state:
            for k in self.orientaion_widget.keys():
                if k != key:
                    self.orientaion_widget[k].children()[2].blockSignals(True)
                    self.orientaion_widget[k].children()[2].setChecked(False)     # Radiobox in layout
                    self.orientaion_widget[k].children()[2].blockSignals(False)
            self.cfg.x_anatomical_direction = orientations['x']
            self.cfg.y_anatomical_direction = orientations['y']
            self.cfg.z_anatomical_direction = orientations['z']

        else:

            self.cfg.x_anatomical_direction = ''
            self.cfg.y_anatomical_direction = ''
            self.cfg.z_anatomical_direction = ''

        print(self.cfg.x_anatomical_direction,self.cfg.y_anatomical_direction,self.cfg.z_anatomical_direction)