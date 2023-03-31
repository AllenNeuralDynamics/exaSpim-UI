from PyQt5.QtCore import Qt
from qtpy.QtWidgets import  QMessageBox, QLineEdit, QVBoxLayout, QWidget, \
    QHBoxLayout, QLabel, QDoubleSpinBox,  QScrollArea, QFrame, QSpinBox, QSlider,\
    QComboBox
import qtpy.QtCore as QtCore

class WidgetBase:

    def config_change(self, value, path, dict):

        """Changes instrument config when a changed value is entered
        :param value: value from dial widget
        :param path: path to value in cfg
        :param dict: dictionary in cfg where value is saved"""

        cfg_value = self.pathGet(dict, path)
        value_type = type(cfg_value)
        value = float(value)
        if cfg_value != value:
            self.pathSet(dict, path, value)
            if self.instrument.livestream_enabled.is_set():
                self.instrument._setup_waveform_hardware(self.instrument.active_lasers, live=True)

    def update_layer(self, args):

        """Update viewer with new multiscaled camera frame"""
        (image, layer_num) = args

        try:
            layer = self.viewer.layers[f"Video {layer_num}"]
            layer.data = image
        except:
            # Add image to a new layer if layer doesn't exist yet
            self.viewer.add_image(image, name=f"Video {layer_num}",
                                  multiscale=True,
                                  scale=self.scale)
            self.viewer.layers[f"Video {layer_num}"].blending = 'additive'

    def scan(self, dictionary: dict, attr: str, prev_key: str = None, QDictionary: dict = None,
             WindowDictionary: dict = None, wl: str = None, input_type: str = QLineEdit, subdict: bool = False):

        """Scanning function to scan through dictionaries and create QWidgets for labels and inputs
        and save changes to config when done editing
        :param dictionary: dictionary which to scan through
        :param attr: attribute of config object
        :param QDictionary: dictionary which to place widgets
        :param WindowDictionary: dictionary which hols all the formatted widgets
        :param wl: specifies which wavelength parameter will map to
        :param input_type: type of QWidget that the input will be formatted to. Default is QLineEdit. Can support...
        :param subdict: if true, subdictionaries will also be scanned through. If false, those keys will be skipped
         """

        QDictionary = {} if QDictionary is None else QDictionary
        WindowDictionary = {} if WindowDictionary is None else WindowDictionary
        prev_key = '' if prev_key is None else prev_key

        for keys in dictionary.keys():
            if type(dictionary[keys]) != dict:

                new_key = f'{prev_key}_{keys}' if keys in QDictionary or subdict else keys
                QDictionary[new_key + '_label'], QDictionary[new_key] = self.create_widget(
                    dictionary[keys], input_type, label=new_key)
                QDictionary[new_key].editingFinished.connect((lambda widget=QDictionary[new_key], kw=keys:
                                                              self.config_change(widget, attr, kw, wl)))

                WindowDictionary[new_key] = self.create_layout(struct='H', label=QDictionary[new_key + '_label'],
                                                               text=QDictionary[new_key])

            elif subdict:
                self.scan(dictionary[keys], attr, keys, QDictionary, WindowDictionary, wl=wl, subdict=True)

        return WindowDictionary

    def scroll_box(self, widget: QWidget):

        """Create a scroll box area to put large vertical widgets.
        :param widget: QWidget that holds multiple widgets in a set layout"""

        scroll = QScrollArea()
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidgetResizable(True)
        scroll.setWidget(widget)
        #scroll.setMinimumHeight(300)
        return scroll

    def adding_tabs(self, dock: dict, viewer):

        """Adds tabs to main dock in napari
        :param dock: dictionary of all the docks that you want to tabify in correct order
        :param viewer: napari viewer
        """
        keys = dock.keys()

        i = 1
        while i < len(keys):
            viewer.window._qt_window.tabifyDockWidget(dock[keys[0]], dock[keys[i]])

    def set_attribute(self, obj: object, var: str, widget: QWidget):

        """Sets an attribute value in the config object
        :param obj: object usually the config
        :param var: variable in the object to set
        :param widget: the widget that holds the new value to set to"""

        value_type = type(getattr(obj, var))
        value = value_type(widget.text())

        if getattr(obj, var, value) != value:

            setattr(obj, var, value)
            if self.instrument.livestream_enabled.is_set():
                self.instrument.apply_config()

    def error_msg(self, title: str, msg: str):

        """Easy way to display error messages
        :param title: title of error message
        :param msg: message to display in the error message"""

        error = QMessageBox()
        error.setWindowTitle(title)
        error.setText(msg)
        error.exec()

    def pathFind(self, dictionary: dict, kw: str, path: list = None, preset_path: bool = False):

        """A recursive function to find the path to a keyword in a nested dictionary and returns a list of the path
        :param dictionary: dictionary which contains the keyword
        :param kw: keyword
        :param path: path to some subdictionary. Default is none
        :param preset_path: a boolean indicating if the  """

        if path is None:
            path = []

        if preset_path:
            dictionary = self.pathGet(dictionary, path)
            preset_path = False
            path = []

        for keys in dictionary.keys():
            if keys == kw:
                path.append(keys)
                return path

            elif type(dictionary[keys]) == dict and kw not in path:
                path.append(keys)
                self.pathFind(dictionary[keys], kw, path)
                if path[-1] != kw:
                    del path[-1]
                else:
                    return path

    def pathGet(self, dictionary, path):

        """Returns subdictionary based on a given path"""

        if path is None:
            return dictionary

        else:
            for k in path:
                dictionary = dictionary[k]
            return dictionary

    def pathSet(self, dictionary, path, setItem):

        """Set subdictionary value based on a path to the keyword"""

        key = path[-1]
        dictionary = self.pathGet(dictionary, path[:-1])
        dictionary[key] = setItem

    def create_layout(self, struct: str, **kwargs):

        """Creates either a horizontal or vertical layout populated with widgets
        :param struct: specifies whether the layout will be horizontal, vertical, or combo
        :param kwargs: all widgets contained in layout"""

        layouts = {'H': QHBoxLayout(), 'V': QVBoxLayout()}
        widget = QFrame()
        if struct == 'V' or struct == 'H':
            layout = layouts[struct]
            for arg in kwargs.values():
                layout.addWidget(arg)

        elif struct == 'VH' or 'HV':
            bin0 = {}
            bin1 = {}
            j = 0
            for v in kwargs.values():
                bin0[str(v)] = v
                j += 1
                if j == 2:
                    j = 0
                    bin1[str(v)] = self.create_layout(struct=struct[0], **bin0)
                    bin0 = {}
            return self.create_layout(struct=struct[1], **bin1)

        layout.setContentsMargins(0, 0, 0, 0)
        widget.setLayout(layout)
        return widget

    def label_maker(self, string: str):

        """Removes underscores and capitalizes words in variable names"""

        variable_names = {'um':'[um]', 's':'[s]', 'us':'[us]', 'v':'[V]', 'hz':'[Hz]',
                          'pixels':'[px]', 'pix':'[px]', 'percent':'[%]', 'px':'[px]'}

        for key, value in variable_names.items():
            if key in string and string.rfind(key) == (len(string)-len(key)):
                string = value.join(string.rsplit(key, 1))

        label = string.split('_')
        label = [words.capitalize() for words in label]
        label = " ".join(label)
        return label

    def create_widget(self, value, Qtype, label):

        """Create a label and input box for a variable
         :param label: variable to create unique label
         :param value: value to preset input widget value
         :param Qtype: type of QWidget """

        label = self.label_maker(label)

        widget_label = QLabel(label)
        widget_input = Qtype()
        if isinstance(widget_input, QDoubleSpinBox):
            widget_input.setValue(value)
            widget_input.setSingleStep(.01)

        elif isinstance(widget_input, QLineEdit):
            widget_input.setText(str(value))

        elif isinstance(widget_input, QSpinBox):
            widget_input.setMaximum(2147483647)
            widget_input.setMinimum(-2147483648)
            widget_input.setValue(int(value))

        elif isinstance(widget_input, QSlider):
            widget_input.setOrientation(QtCore.Qt.Horizontal)

        return widget_label, widget_input
