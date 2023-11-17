#!/usr/bin/env python3

import csv
from glob import glob
from itertools import groupby, islice
import os
from pathlib import Path
import re
import sys
from collections import defaultdict, OrderedDict
from enum import Enum
from typing import *

_run = "{run}"
__fallback_run_name = "run1"
__default_path_template = "{out_prefix}{run}_{layout}.tsv"
__format_keys = ["single_header", "paired_header", "delimiter",
                 "absolute_paths", "current_dir_placeholder", "home_placeholder"]
__required_format_keys = __format_keys[:2]



class Layout(Enum):
    SINGLE = 1
    SINGLE_REV = -1
    PAIRED = 3

    def __str__(self):
        return self.name.lower()


class Run(object):
    def __init__(self, name, layout, samples):
        self.name = name
        self.layout = layout
        self.samples = samples
        assert isinstance(layout, Layout)
        self.n_reads = 2 if layout == Layout.PAIRED else 1


class SamplePatternMismatch(Exception):
    def __init__(self, sample, pattern, pattern_name=None, *args, **kwargs):
        msg = (
            'Sample name "{}" not matched by {}. Is '
            'the sample_pattern option correctly specified? '
            'Note that if specifying a directories list as input,'
            'all files need to be actual read files. For example, Illumina '
            'index files in the same directories could as well cause this error.\n'
            'Regex patterns can be tested e.g. on https://regex101.com or https://regexr.com'
        ).format(
            sample, pattern,
            f"the regular expression '{pattern}'" if pattern_name is None \
            else f"the '{pattern_name}' pattern (regular expression: {pattern})"
        )
        super().__init__(msg, *args, **kwargs)


def format_list(l, cutoff=10):
    out = ", ".join(str(item) for item in islice(l, 10))
    if len(l) > cutoff:
        out += '...'
    return out


class RunWildcard(object):
    """
    Expands run wildcards in paths
    """

    def __init__(self, path, from_end=False):
        path = Path(path)
        parts = list(path.parts)
        n_parts = len(parts)
        run_escaped = re.sub(r"[\{\}]", "\\\\\g<0>", _run)
        patterns = [(i, re.compile(re.escape(p).replace(run_escaped, '(.+?)')))
                    for i, p in enumerate(parts) if _run in p]
        assert len(patterns) == 1, \
            f"Invalid number of {_run} wildcards (only one allowed)"
        self.pat_idx, self.pattern = patterns[0]
        if from_end:
            self.pat_idx = self.pat_idx - n_parts
        parts[self.pat_idx] = parts[self.pat_idx].replace(_run, "*")
        self.glob_pattern = os.path.join(*parts)

    def get_run(self, path):
        path = Path(path)
        parts = list(path.parts)
        return self.pattern.fullmatch(parts[self.pat_idx]).group(1)


def _run_from_dir(d, override=None):
    if override is not None:
        return override
    return None if d.name in (".", "") else d.name


def expand_file_pattern(
        pattern: str,
        recursive: bool = False,
        run_override: Optional[str] = None
    ) -> Generator[Tuple[Optional[str], Path], None, None]:
    # parse run wildcard
    run_wildcard = None
    n = pattern.count(_run)
    if n > 0:
        assert run_override is None, (
            f"Run '{run_override}' was specified manually, but the {_run} "
            f"wildcard was also found in the pattern: '{pattern}'. "
            "One of them should be omitted.")
    assert n <= 1, f"Too many {_run} wildcards (only one allowed)"
    if n == 1:
        if recursive:
            parts = pattern.split("**")
            if _run in parts[0]:
                run_wildcard = RunWildcard(parts[0])
                parts[0] = run_wildcard.glob_pattern
            else:
                assert _run in parts[-1], (
                    f"The {_run} wildcard cannot be in the middle between two "
                    "recursive /**/ expressions, it must be in the first or last "
                    "part of the pattern.")
                run_wildcard = RunWildcard(parts[-1], from_end=True)
                parts[-1] = run_wildcard.glob_pattern
            pattern = "**".join(parts)
        else:
            run_wildcard = RunWildcard(pattern)
            pattern = run_wildcard.glob_pattern

    # do the glob search
    for path in glob(pattern, recursive=recursive):
        p = Path(path)
        if run_wildcard is None:
            run = _run_from_dir(p.parent, run_override)
        else:
            run = run_wildcard.get_run(path)
        yield run, p


def _list_files(directory):
    for name in os.listdir(directory):
        path = directory / Path(name)
        if path.is_file():
            yield path


def list_dir(
        directory: str,
        recursive: bool = False,
        run_override: Optional[str] = None
    ) -> Generator[Tuple[Optional[str], Path], None, None]:
    if _run in directory:
        # run wildcard present
        assert run_override is None, (
            f"Run '{run_override}' was specified manually, but the {_run} "
            f"wildcard was also found in the directory: '{directory}'. "
            "One of them should be omitted.")
        w = RunWildcard(directory)
        for path in glob(w.glob_pattern):
            if os.path.isdir(path):
                run = w.get_run(path)
                for path in _list_files(path):
                    yield run, path
    elif recursive is True:
        for root, _dirnames, filenames in os.walk(directory):
            root = Path(root)
            run = _run_from_dir(root, run_override)
            for path in filenames:
                yield run, root.joinpath(path)
    else:
        for path in _list_files(directory):
            run = _run_from_dir(path.parent, run_override)
            yield run, path



def _unpack_run(input):
    if isinstance(input, (tuple, list)):
        assert len(input) == 2
        return input
    return None, input


def collect_files(
        directories: Optional[Iterable[Union[str, Tuple[str, str]]]] = None,
        patterns: Optional[Iterable[Union[str, Tuple[str, str]]]] = None,
        recursive: bool = False,
        sample_ext: Optional[Container[str]] = None,
) -> Generator[Tuple[Optional[str], Path], None, None]:
    """
    Collects all input files, given a sequence of 
    directories and/or a sequence of glob patterns.
    Relative paths will be interpreted relative to
    `base_dir`.
    The generator yields the individual file paths.
    """
    if directories is None and patterns is None:
        raise Exception(
            'At least one of "directories" and "patterns" must be defined in "input"')
    if patterns is not None:
        for pattern in patterns:
            run_override, pattern = _unpack_run(pattern)
            found = False
            for run, path in expand_file_pattern(pattern, recursive, run_override=run_override):
                if path.is_file():
                    yield run, path
                    found = True
            assert found, "Pattern had no matches: '{}'".format(pattern)

    if directories is not None:
        for _dir in directories:
            run_override, _dir = _unpack_run(_dir)
            found = False
            for run, f in list_dir(_dir, recursive, run_override=run_override):
                if f.is_file() and (sample_ext is None or any(f.name.endswith(ext) for ext in sample_ext)):
                    found = True
                    yield run, f
            assert found, (
                f"No file found in '{_dir}'. Maybe the allowed file extensions are "
                "too restrictive, or you meant to enable recursive search?")


def parse_sample_pattern(sample_name, pattern, reserved_pattern=None) -> Tuple[str, int, bool]:
    """
    Matches sample name and read number in a file name, given a
    name pattern.
    """
    m = pattern.fullmatch(sample_name)
    if m is None:
        raise SamplePatternMismatch(sample_name, pattern.pattern)
    try:
        sample_name = m.group(1)
    except IndexError:
        sample_name = m.group("sample")
    try:
        read = m.group(2)
    except IndexError:
        try:
            read = m.group("read")
        except AttributeError:
            # assuming no read group
            read = '1'
    assert (sample_name is not None and read is not None), (
        "Regular expression in 'sample_pattern' needs at least one group "
        "matching the sample name, and an optional second group matching "
        "the read number. They can also be named: (?P<sample>...) and (?P<read>...)")
    assert (read in ('1', '2')), \
        'Read number in file name must be 1 or 2, found instead "{}". ' \
        'Is the Regex pattern (sample_pattern) correct?'.format(read)
    # rename if necessary
    renamed = False
    if reserved_pattern is not None:
        sample_name, n = reserved_pattern.subn("_", sample_name)
        renamed = n > 0
    return sample_name, int(read), renamed


def _is_valid_sample_pattern(*args, **kwargs):
    try:
        parse_sample_pattern(*args, **kwargs)
        return True
    except:
        return False


def collect_samples(sample_pattern: str, reserved_chars=None, **param) -> Tuple[str, Optional[str], Path, int]:
    """
    This function collects sample files from `directories` and `patterns`
    (see `_collect_files`) and parses the sample names given using
    a defined pattern (see `parse_pattern`), optionally normalizing problematic
    characters.
    The generator yields a tuple of (sample name,  run name, file name, read number),
    whereby read number is 1 or 2.
    """
    _name_pat = re.compile(sample_pattern)
    _reserved_pat = None if reserved_chars is None else re.compile(
        "[{}]".format(reserved_chars))
    renamed_samples = []
    for run, f in collect_files(**param):
        sample_name, read, renamed = parse_sample_pattern(
            os.path.basename(f), _name_pat, reserved_pattern=_reserved_pat)
        if renamed:
            renamed_samples.append(sample_name)
        yield sample_name, run, f, read
    if renamed_samples:
        renamed_samples = list(OrderedDict(
            zip(renamed_samples, renamed_samples)).keys())
        print(("Problematic characters in sample names were replaced by "
               "underscores: {}").format(format_list(renamed_samples)),
              file=sys.stderr)


def get_grouped(
        paired_filter: Optional[str] = None,
        make_unique: bool = False,
        quiet: bool = False,
        **collect_args
) -> Dict[           # grouped by run name
    Optional[str],
    Dict[            # grouped by layout
        Layout,    
        Dict[        # paths grouped by sample name
            str,         
            Tuple[Path]  # [forward, (reverse)]
        ]
    ]
]:
    # (1) group files by run, then by sample name
    # TODO: defaultdict is only sorted in recent Python versions
    by_run = defaultdict(lambda: defaultdict(set))
    for sample, run, filename, read in collect_samples(**collect_args):
        by_run[run][sample].add((filename, read))

    # (2) sort the files and check for duplicates
    run_list = []
    for run, by_sample in by_run.items():
        file_list = []
        for sample, read_files in by_sample.items():
            # sort the unique files (which were stored in a set):
            # first by directory path, then by read index.
            # > 2 files from the same sample in the same directory are not allowed,
            # there will be an error, so the file name itself does not need to
            # contribute to the sorting.
            read_files = sorted(read_files, key=lambda k: (k[0].parent, k[1]))
            # split into read indices and read paths
            paths, read_idx = zip(*read_files)
            # check for duplicates
            if sorted(set(read_idx)) == sorted(read_idx):
                file_list.append((sample, paths, read_idx))
            elif make_unique:
                # Split the directory-sorted paths (no need to create another dict)
                # to obtain unique R1-(R2) files
                for i, data in enumerate(groupby(read_files, lambda k: k[0].parent)):
                    dirname, file_group = data
                    paths, read_idx = zip(*file_group)
                    assert sorted(set(read_idx)) == list(read_idx), (
                        "Could not obtain unique sample name for files because "
                        "there are duplicates within the same directory. This is "
                        f"not allowed: \n{dirname}")
                    unique_sample = f"{sample}_{i+1}"
                    file_list.append((unique_sample, paths, read_idx))
            else:
                raise Exception((
                "Several files were found for sample '{}'. Was it sequenced "
                "in different runs or could there be a name clash? "
                "Also, check the sample pattern, did it correctly recognize "
                "the name? If so, you can either enable 'make_unique' "
                "or use the {} wildcard to output one file per run. "
                "The problematic files:\n{}"
                ).format(sample, _run, format_list(paths)))
        run_list.append((run, file_list))
    
    # (3) determine the read layout and group by run -> read layout -> sample
    out = OrderedDict()
    r2_only = []
    for run, file_list in run_list:
        by_layout = out[run] = OrderedDict((
            (Layout.SINGLE, OrderedDict()), 
            (Layout.SINGLE_REV, OrderedDict()), 
            (Layout.PAIRED, OrderedDict())
        ))
        for sample, paths, read_idx in file_list:
            # handle paired-filter
            if paired_filter is not None:
                if paired_filter == "forward":
                    if read_idx[0] == 2:  # only R2 present, nothing to return
                        continue
                    paths = [paths[0]]
                    read_idx = [read_idx[0]]
                else:
                    assert paired_filter == "reverse", \
                        f"Invalid value for 'paired_filter': {paired_filter}"
                    if read_idx[-1] == 1:  # only R1 present, nothing to return
                        continue
                    paths = [paths[-1]]
                    read_idx = [read_idx[-1]]
            # now, we can determine the output layout
            n_reads = len(read_idx)
            if n_reads == 2:
                # paired-end
                assert read_idx == (1, 2), (
                    f"Two read files present for sample {sample}, but read "
                    f"numbers are {read_idx[0]} and {read_idx[1]} instead of "
                    "1 and 2")
                if paired_filter is None:
                    layout = Layout.PAIRED
                else:
                    if paired_filter == "forward":
                        layout = Layout.SINGLE
                        paths = [paths[0]]
                    else:
                        layout = Layout.SINGLE_REV
                        assert paired_filter == "reverse", \
                            f"Invalid value for 'paired_filter': {paired_filter}"
                        paths = [paths[1]]
            else:
                # single-end
                assert n_reads == 1
                if read_idx[0] == 1:
                    layout = Layout.SINGLE
                else:
                    assert read_idx[0] == 2
                    if paired_filter != "reverse":
                        r2_only.append(sample)
                    layout = Layout.SINGLE_REV
            # store in dict
            by_layout[layout][sample] = paths
            # # some extra checks for program correctness
            # assert make_unique and all(re.sub("_\d+$", "", sample) in p.name for p in paths) \
            #     or all(sample in p.name for p in paths)
            if len(paths) == 2:
                assert paths[0].parent == paths[1].parent

    if r2_only:
        print(("Warning: Only reverse read file (No. 2) present for some samples, "
               "is this correct?\n{}").format(format_list(r2_only)),
              file=sys.stderr)
    return out


def get_runs(
        default_run=__fallback_run_name,
        **search_settings
    ) -> Generator[Run, None, None]:
    run_data_grouped = get_grouped(**search_settings)
    for run, by_layout in run_data_grouped.items():
        if run is None:
            run = default_run
        for layout, samples in by_layout.items():
            if len(samples) > 0:
                yield Run(run, layout, list(samples.items()))


def _read_config(*paths):
    out = {}
    if paths:
        try:
            import tomllib
        except ModuleNotFoundError:
            try:
                import tomli as tomllib
            except ImportError:
                print("Cannot pattern/format configuration files since the "
                    "necessary Python module is missing. Either upgrade to Python 3.11 "
                    "or install the 'tomli' library, e.g. using "
                    "'pip3 install --user tomli'")
        for path in paths:
            if path is not None and os.path.exists(path):
                with open(path, "rb") as f:
                    d = tomllib.load(f)
                    out.update(d)
    return out


def read_config(filename, *other_config):
    default_cfg = os.path.join(os.path.dirname(__file__), filename)
    return _read_config(default_cfg, *other_config)


def read_pattern_config(*other_config):
    return read_config("sample_patterns.toml", *other_config)


def read_format_config(*other_config):
    return read_config("formats.toml", *other_config)


def get_sample_regex(
        pattern,
        *other_paths,
        check_max=1000,
        quiet = False,
        **collect_args):
    """"
    Returns a regex sample pattern given a pattern name
    (searching for named patterns in all config files)
    If the name is not found, we just assume it's already a regex pattern.
    """
    cfg = read_pattern_config(*other_paths).items()
    cfg = {name: re.compile(patt) for name, patt in cfg}
    if pattern is None:
        # try to infer the pattern using file names
        assert len(cfg) > 0, (
            "No sample pattern supplied and no TOML pattern lists available, "
            "from which the pattern could be guessed")
        files = [p.name for _, p in 
                 islice(collect_files(**collect_args), check_max)]
        valid = [name for name, patt in cfg.items()
                 if all(_is_valid_sample_pattern(f, patt) for f in files)]
        if len(valid) == 1:
            name = next(iter(valid))
            if not quiet:
                print(f"Automatically inferred sample pattern: '{name}'", file=sys.stderr)
            return cfg[name]
        n = len(files)
        if len(valid) > 1:
            valid_list = ", ".join(f"'{v}'" for v in valid)
            raise Exception(
                "No sample pattern supplied, and several known patterns match "
                f"the {n} tested file names: {valid_list}. Please specify the "
                "correct sample pattern name."
            )
        raise Exception(
            f"No sample pattern supplied, and no known pattern matches the {n} "
            "tested file names."
        )
    try:
        return cfg[pattern]
    except KeyError:
        return re.compile(pattern)


def get_format_config(format, *other_paths, **default_settings):
    """"
    Returns a format configuration given a format name
    (searching for named patterns in all config files)
    """
    cfg = read_format_config(*other_paths)
    try:
        cfg = {k.replace('-', '_'): v for k, v in cfg[format].items()}
    except KeyError:
        raise Exception(f"Unknown format: '{format}'")
    s = set(cfg)
    invalid = s.difference(__format_keys)
    assert len(invalid) == 0, \
        "Invalid format settings in '{}' configuration: {}".format(format, format_list(invalid))
    missing = set(__required_format_keys).difference(s)
    assert len(missing) == 0, \
        "Format settings missing from '{}' configuration: {}".format(format, ", ".join(missing))
    default_settings.update(cfg)
    return default_settings


def _normalize_paths(
        paths: Iterable[Path],
        absolute_paths = False, 
        current_dir_placeholder: str = None,
        home_placeholder: str = None):
    if absolute_paths:
        if current_dir_placeholder is not None:
            paths = [current_dir_placeholder / p if not p.is_absolute() else p for p in paths]
        else:
            paths = [p.resolve() for p in paths]
        if home_placeholder is not None:
            h = Path.home()
            paths = [home_placeholder / p.resolve().relative_to(h)
                     if p.is_absolute() and h in p.parents  # TODO: is_relative_to() (since 3.9)
                     else p
                     for p in paths]
    return paths


def write_sample_files(
        runs: Iterable[Run],
        out_prefix: str,
        single_header: str,
        paired_header: str,
        delimiter: str = '\t',
        path_template: str = __default_path_template,
        default_run: str = __fallback_run_name,
        quiet: bool = False,
        **path_settings):
    header_map = {
        Layout.SINGLE: single_header,
        Layout.SINGLE_REV: single_header,
        Layout.PAIRED: paired_header
    }
    unique_paths = set()  # for detecting duplicates
    for run in runs:
        if run.name is None:
            run.name = default_run
        if len(run.samples) > 0:
            # determine output path and its uniqueness
            outfile = path_template \
                .format(out_prefix=out_prefix, layout=run.layout, run=run.name) \
                .replace('/', os.sep)
            outfile = os.path.abspath(outfile)
            assert not outfile in unique_paths, (
                f"File {outfile} already exists. It seems like the path template "
                "is missing the {layout} or {run} wildcard.")
            unique_paths.add(outfile)
            d = os.path.dirname(outfile)
            if d and not os.path.exists(d):
                os.makedirs(d)
            # write to file
            if not quiet:
                print("{} samples from '{}' ({}-end) written to {}".format(
                    len(run.samples), run.name, run.layout, os.path.relpath(outfile)
                ), file=sys.stderr)
            with open(outfile, "w") as out:
                w = csv.writer(out, delimiter=delimiter)
                header = header_map[run.layout]
                assert len(header) == run.n_reads + 1, \
                    "{}-end header does not have {} fields: {}".format(
                        run.layout, run.n_reads+1, ", ".join(header)
                    )
                w.writerow(header)
                for sample, paths in run.samples:
                    paths = _normalize_paths(paths, **path_settings)
                    w.writerow([sample] + list(paths))


def make_sample_file(
        out_prefix: str,
        format: Union[str, dict],
        directories: Optional[Iterable[Union[str, Tuple[str, str]]]] = None,
        patterns: Optional[Iterable[Union[str, Tuple[str, str]]]] = None,
        recursive: bool = False,
        sample_ext: Optional[Container[str]] = None,
        sample_pattern: Optional[str] = None,
        path_template: str = __default_path_template,
        default_run: str = __fallback_run_name,
        pattern_files: str = None,
        format_config_files: str = None,
        default_format_settings: Optional[dict] = None,
        quiet: bool = False,
        **collect_args):
    # get format configuration
    format_settings = format
    if not isinstance(format_settings, dict):
        assert isinstance(format_settings, str), "Format name is not a string"
        format_settings = get_format_config(format, *format_config_files, **default_format_settings)

    # collect sample files
    sample_pattern = get_sample_regex(
        sample_pattern,
        directories=directories,
        patterns=patterns,
        recursive=recursive,
        sample_ext=sample_ext,
        quiet=quiet,
        *pattern_files
    )
    runs = get_runs(
        directories=directories,
        patterns=patterns,
        recursive=recursive,
        sample_ext=sample_ext,
        sample_pattern=sample_pattern,
        quiet=quiet,
        **collect_args)
    # write to disk
    write_sample_files(
        runs,
        out_prefix,
        path_template=path_template,
        default_run=default_run,
        quiet=quiet,
        **format_settings
    )


def main(args=sys.argv[1:]):
    import argparse
    from functools import partial
    comma_list = partial(str.split, sep=',')
    def _arg(text):
        s = text.split("=", 1)
        if len(s) == 2:
            return s
        return (None, text)

    p = argparse.ArgumentParser(
        description="Script for making a manifest file as input for amplicon pipelines such as QIIME",
        usage="%(prog)s [-d DIRECTORY, [DIRECTORY, ...] | -p PATTERN, [PATTERN, ...], ...] [-r] [other options]"
    )

    s = p.add_argument_group("Search settings")
    s.add_argument("-d", "--directory", dest="directories", metavar="DIR",
                   type=_arg, nargs="*",
                   help="Directory in which to look for FASTQ files. "
                   "Only files matching '-e/--sample-ext' will be included. "
                   "By default, the directory name will be used as run name. "
                   "To change this, you can manually specify the run like this: "
                   "'-d run_name=/path/to/directory'. "
                    "Multiple paths can be added in order to look in several "
                    "directories.")
    s.add_argument("-p", "--pattern", dest="patterns",
                   type=_arg, nargs="*",
                   help="Glob pattern for finding FASTQ files. "
                   "By default, the directory name will be used as run name. "
                   "To change this, you can manually specify the run like this: "
                   "'-p run_name=<file pattern>'. "
                    "Multiple patterns/paths delimited by spaces can be added.")
    s.add_argument("-r", "--recursive", action="store_true",
                   help="Search directories recursively and/or match glob patterns "
                    "recursively (unlimited directory depth, specified using /**/)")
    s.add_argument("-e", "--sample-ext", type=comma_list, metavar="EXTENSION",
                   default=[".fastq.gz", ".fq.gz"],
                   help="Comma delimited list of valid file extension(s) in "
                   "directories (default: '.fastq.gz,fq.gz')")

    n = p.add_argument_group("Settings regarding sample names")
    n.add_argument("--reserved", dest="reserved_chars", metavar="CHARS", default="-. ",
                   help="List of reserved characters in sample names, "
                        "which will be converted to underscores. "
                        "Default: '-. '")
    n.add_argument("-s", "--sample-pattern", metavar="PATTERN",
                   help="Sample pattern: either a named pattern or a regular "
                   "expression matching the *whole* sample file name "
                   "(default: guess the pattern). "
                    "Possible valid patterns are defined in sample_patterns.toml and/or "
                    "a custom configuration file supplied with --pattern-file. "
                    "If not in the list of named patterns, it is assumed to be "
                    "a Regex pattern with at least one group matching the "
                    "sample name, and an optional second group matching "
                    "the read number. Patterns can also be named: "
                    "(?P<sample>...) and (?P<read>...).")
    n.add_argument("--pattern-file", dest="pattern_files", metavar="FILE",
                   action="append", default=[],                   
                   help="Path to an (additional) format configuration file")

    o = p.add_argument_group("Output settings")
    o.add_argument("-o", "--out_prefix", default="samples_", metavar="PREFIX",
                   help="Output prefix for sample files files."
                    "With the default prefix ('samples_') and a single run, the "
                    f"output will be samples_single_{__fallback_run_name}.tsv or "
                    f"manifest_paired_{__fallback_run_name}.tsv. "
                    "See also --path-template for more options on output paths.")
    o.add_argument("-f", "--format",
                   help="Output format name. Possible formats are listed in "
                   "formats.toml and/or custom configuration files supplied with "
                   "--format-config-file. Alternatively, format settings "
                   "can be manually specified (see 'output format settings').")
    o.add_argument("-u", "--make-unique", action="store_true",
                   help="Make identical sample names unique instead of returning "
                   "an error. Duplicate names can occur if the same sample was "
                   "sequenced in several runs, or if there are name clashes across "
                   "runs. The -u flag can be supplied if multiple runs should "
                   "be analyzed together (treated as a single run).")
    o.add_argument("--path-template", default=__default_path_template, metavar="STRING",
                   help="Template for creating the sample file(s). "
                        "Subdirectories are automatically created.")
    o.add_argument("--paired-filter", choices={"forward", "reverse"},
                   help="Keep only forward/R1 or reverse/R2 read files in a "
                   "paired layout, resulting in a single-end layout file. "
                   "If only keeping reverse/R2 reads, the resulting layout name "
                   "is 'single_rev'.")
    
    f = p.add_argument_group(
        "Output format settings",
        description="Manual format settings, must be specified if -f/--format "
        "was not supplied")
    f.add_argument("--format-config-file", dest="format_config_files", metavar="FILE",
                   action="append", default=[],
                   help="Path to an (additional) format configuration file")
    f.add_argument("--sh", "--single-header", dest="single_header",
                   metavar="FIELDS", type=comma_list,
                   help="Single-end manifest header (comma delimited list). ")
    f.add_argument("--ph", "--paired-header", dest="paired_header",
                   metavar="FIELDS", type=comma_list,
                   help="Single-end manifest header (comma delimited list). ")
    f.add_argument("--delim", "--delimiter", dest="delimiter",
                   default="\t",
                   help="Output delimiter (default: \\t=tab character)")
    f.add_argument("-a", "--absolute-paths",
                   action="store_true",
                   help="Enforce listing files as absolute paths, even if the "
                   "input directories/patterns were relative paths.")
    f.add_argument("--current-dir-placeholder", metavar="PLACEHOLDER",
                   help="Placeholder for the current directory, which is inserted"
                   "in relative paths. Some formats such as QIIME allow for $PWD "
                   "as placeholder.")
    f.add_argument("--home-placeholder", metavar="PLACEHOLDER",
                   help="Placeholder for the home directory, which is inserted"
                   "in absolute paths. Some formats such as QIIME allow for $HOME "
                   " as placeholder.")
    
    other = p.add_argument_group("Other settings")
    other.add_argument("-q", "--quiet", action="store_true",
                   help="Don't print any information (except for warnings)")
    
    args = p.parse_args(args)
    args = vars(args)

    try:
        # validate
        assert args["directories"] is not None or args["patterns"] is not None, \
            "Please specify at least one -d/--directory or -p/--pattern"

        fmt_args = {}
        for var in __format_keys:
            fmt_args[var] = args.pop(var, None)
        args["default_format_settings"] = fmt_args
        if args["format"] is None:
            assert fmt_args["single_header"] is not None and fmt_args["paired_header"] is not None, (
                "Either -f/--format or --sh/--single-header and --ph/--paired-header "
                "must be supplied. Available formats are: {}".format(
                    format_list(read_format_config(*args["format_config_files"]))
                ))
        # run
        make_sample_file(**args)

    except Exception as e:
        print(f"Error: {e}\n\n", file=sys.stderr)
        p.print_help()
        exit(1)


if __name__ == "__main__":
    main()
