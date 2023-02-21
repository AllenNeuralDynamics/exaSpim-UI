from widgets.widget_base import WidgetBase
from qtpy.QtWidgets import QLineEdit, QVBoxLayout, QWidget, \
    QHBoxLayout, QLabel, QDoubleSpinBox, QComboBox
from qtpy.QtGui import QIntValidator


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


    def scan_config(self, config: object):

        """Scans config and finds property types with setter and getter attributes
        :param config: config object from the instrument class"""

        imaging_specs_widgets = {}  # dictionary that holds layout of attribute labels/input pairs

        cpx_attributes = ['exposure_time_s', 'slit_width_pix', 'line_time_us', 'scan_direction_left',
                          'scan_direction_right']

        for attr in dir(config):
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


