""" Tablib - formats
"""

__lazy_modules__ = {
    "functools",
    "importlib",
    "importlib.util",
    "tablib.exceptions",
    "tablib.formats._csv",
    "tablib.formats._json",
    "tablib.formats._tsv",
    "tablib.utils",
}

from functools import partialmethod
from importlib import import_module
from importlib.util import find_spec

from ..exceptions import UnsupportedFormat
from ..utils import normalize_input
from ._csv import CSVFormat
from ._json import JSONFormat
from ._tsv import TSVFormat

uninstalled_format_messages = {
    "cli": {"package_name": "tabulate package", "extras_name": "cli"},
    "df": {"package_name": "pandas package", "extras_name": "pandas"},
    "ods": {"package_name": "odfpy package", "extras_name": "ods"},
    "xls": {"package_name": "xlrd and xlwt packages", "extras_name": "xls"},
    "xlsx": {"package_name": "openpyxl package", "extras_name": "xlsx"},
    "yaml": {"package_name": "pyyaml package", "extras_name": "yaml"},
}


def load_format_class(dotted_path):
    """Import and return the format class at the given dotted path.

    ``dotted_path`` is the fully qualified name of the class, e.g.
    ``'tablib.formats._xlsx.XLSXFormat'``. Raises ``ImportError`` if
    the path cannot be resolved to a class.
    """
    try:
        module_path, class_name = dotted_path.rsplit('.', 1)
        return getattr(import_module(module_path), class_name)
    except (ValueError, AttributeError) as err:
        raise ImportError(f"Unable to load format class '{dotted_path}' ({err})")


class FormatDescriptorBase:
    def __init__(self, key, format_or_path):
        self.key = key
        self._format_path = None
        if isinstance(format_or_path, str):
            self._format = None
            self._format_path = format_or_path
        else:
            self._format = format_or_path

    def ensure_format_loaded(self):
        if self._format is None:
            self._format = load_format_class(self._format_path)


class ImportExportBookDescriptor(FormatDescriptorBase):
    def __get__(self, obj, cls, **kwargs):
        self.ensure_format_loaded()
        return self._format.export_book(obj, **kwargs)

    def __set__(self, obj, val):
        self.ensure_format_loaded()
        return self._format.import_book(obj, normalize_input(val))


class ImportExportSetDescriptor(FormatDescriptorBase):
    def __get__(self, obj, cls, **kwargs):
        self.ensure_format_loaded()
        return self._format.export_set(obj, **kwargs)

    def __set__(self, obj, val):
        self.ensure_format_loaded()
        return self._format.import_set(obj, normalize_input(val))


class Registry:
    """Registry of the import/export formats available to Dataset and Databook.

    Each format is registered under a short key (e.g. ``'csv'``,
    ``'xlsx'``). Registering a format adds the corresponding ``<key>``
    property and ``get_<key>`` / ``set_<key>`` methods to
    :class:`tablib.Dataset` and the ``<key>`` property to
    :class:`tablib.Databook`, so a custom format can be used exactly
    like a built-in one. The module-level ``registry`` instance holds
    the formats in use; see "Adding New Formats" in the development
    documentation for a worked example.
    """

    _formats = {}

    def _ensure_builtins_registered(self):
        # Importing tablib.core registers the builtins. It's lazy on Python 3.15+.
        from .. import core  # noqa: F401

    def register(self, key, format_or_path):
        """Register a format under ``key``.

        ``format_or_path`` is either a format instance or the dotted
        path of the format class, which is then imported lazily on
        first use. Registering a format makes it available as a
        ``Dataset.<key>`` / ``Databook.<key>`` property and as
        ``Dataset.get_<key>`` / ``Dataset.set_<key>`` methods.
        """
        from ..core import Databook, Dataset

        # Create Databook.<format> read or read/write properties
        setattr(Databook, key, ImportExportBookDescriptor(key, format_or_path))

        # Create Dataset.<format> read or read/write properties,
        # and Dataset.get_<format>/set_<format> methods.
        setattr(Dataset, key, ImportExportSetDescriptor(key, format_or_path))
        try:
            setattr(Dataset, f'get_{key}', partialmethod(Dataset._get_in_format, key))
            setattr(Dataset, f'set_{key}', partialmethod(Dataset._set_in_format, key))
        except AttributeError:
            setattr(Dataset, f'get_{key}', partialmethod(Dataset._get_in_format, key))

        self._formats[key] = format_or_path

    def register_builtins(self):
        """Register all built-in formats available in this environment.

        Formats whose optional dependencies are not installed (e.g.
        ``xlsx`` without openpyxl) are skipped. Registration order
        matters for format auto-detection: ``xlsx`` is registered
        before ``xls`` because xlrd can also read ``xlsx`` files.
        """
        # Registration ordering matters for autodetection.
        self.register('json', JSONFormat())
        # xlsx before as xls (xlrd) can also read xlsx
        if find_spec('openpyxl'):
            self.register('xlsx', 'tablib.formats._xlsx.XLSXFormat')
        if find_spec('xlrd') and find_spec('xlwt'):
            self.register('xls', 'tablib.formats._xls.XLSFormat')
        if find_spec('yaml'):
            self.register('yaml', 'tablib.formats._yaml.YAMLFormat')
        self.register('csv', CSVFormat())
        self.register('tsv', TSVFormat())
        if find_spec('odf'):
            self.register('ods', 'tablib.formats._ods.ODSFormat')
        self.register('dbf', 'tablib.formats._dbf.DBFFormat')
        self.register('html', 'tablib.formats._html.HTMLFormat')
        self.register('jira', 'tablib.formats._jira.JIRAFormat')
        self.register('latex', 'tablib.formats._latex.LATEXFormat')
        if find_spec('pandas'):
            self.register('df', 'tablib.formats._df.DataFrameFormat')
        self.register('rst', 'tablib.formats._rst.ReSTFormat')
        self.register('sql', 'tablib.formats._sql.SQLFormat')
        if find_spec('tabulate'):
            self.register('cli', 'tablib.formats._cli.CLIFormat')

    def formats(self):
        """Yield the registered format instances, in registration order.

        Built-in formats are registered first if that has not happened
        yet, and formats registered by dotted path are imported on
        first use. Used for format auto-detection; see
        :func:`tablib.detect_format`.
        """
        self._ensure_builtins_registered()
        for key, frm in self._formats.items():
            if isinstance(frm, str):
                self._formats[key] = load_format_class(frm)
            yield self._formats[key]

    def get_format(self, key):
        """Return the format registered under ``key``.

        Formats registered by dotted path are imported on first use.
        Raises :class:`tablib.exceptions.UnsupportedFormat` if no
        format is registered under ``key``, including a hint about the
        optional dependency to install when ``key`` names a known
        format whose package is missing.
        """
        self._ensure_builtins_registered()
        if key not in self._formats:
            if key in uninstalled_format_messages:
                raise UnsupportedFormat(
                    "The '{key}' format is not available. You may want to install the "
                    "{package_name} (or `pip install \"tablib[{extras_name}]\"`).".format(
                        **uninstalled_format_messages[key], key=key
                    )
                )
            raise UnsupportedFormat(f"Tablib has no format '{key}' or it is not registered.")
        if isinstance(self._formats[key], str):
            self._formats[key] = load_format_class(self._formats[key])
        return self._formats[key]


registry = Registry()
