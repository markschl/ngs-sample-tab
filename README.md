# Sample table creator

Many Next-Generation Sequencing (NGS) data analysis pipelines require some kind of delimited file listing the paths of all input files. This script assists with the creation of these files, trying to simplify the process as much as possible.

## What it does

* The script searches one or several input directories for sample files ('.fastq.gz' by default). Alternatively, [glob patterns](https://en.wikipedia.org/wiki/Glob_(programming)) provide a more flexible way of selecting files.
* Sample names are recognized using pre-defined sample patterns (auto-recognized) or a custom supplied regular expression pattern.
* The sample layout (single-end or paired-end) is automatically recognized, and sample lists are generated separately per layout.
* Creating a separate sample file per sequencing run is very easy
* Different output formats are available (or can be manually configured)
* Extensible thanks to configuration files in [TOML](https://toml.io) format, contributions welcome!

## Installation

Installation using `pip`:

```sh
pip install ngs-sample-tab@git+https://github.com/markschl/ngs-sample-tab
```

To use the script, type `make_sample_tab [arguments]`.

Alternatively, just download the contents of the repository, extract `make_sample_tab/make_sample_tab.py` and the two `.toml` files to the current directory and (in UNIX) execute like this: `./make_sample_tab.py [arguments]`.

## Usage

Suppose the following directory structure, containing two runs with overlapping sample names:

```
read_files/
├── run1/
│   ├── a_R1.fastq.gz
│   ├── a_R2.fastq.gz
│   ├── b_R1.fastq.gz
│   └── b_R2.fastq.gz
├── run2/
│   ├── a_R1.fastq.gz
│   └── a_R2.fastq.gz
└── run3/
    ├── x_R1.fastq.gz
    └── y_R1.fastq.gz
```

Sample `a` is present in run 2 as well, the library may have been re-sequenced.


### Simple example (run1)

In order to generate a sample file for `run1`, you can specify its directory using `-d`/`--directory <path>`:

```sh
make_sample_tab -d read_files/run1 -f simple
```

The tool reports:

```
Automatically inferred sample pattern: 'sample_read'
2 samples from 'run1' (paired-end) written to samples_run1_paired.tsv
```

`samples_run1_paired.tsv`:

```
id	R1	R2
a	read_files/run1/a_R1.fastq.gz	read_files/run1/a_R2.fastq.gz
b	read_files/run1/b_R1.fastq.gz	read_files/run1/b_R2.fastq.gz
```

With `-f simple`, we told the tool to use a *simple* tab-delimited output format with a short header, and which allows for relative paths. More on output formats further below.

The run name `run1` is inferred **from the directory name**.

> **_NOTE:_** On **Windows**, both forward (/) and backward (\\) slashes work, they can even be mixed in the same path. 


### Recognition of sample names

When it comes to using this tool, the most tricky part can be the extraction of sample names from file names. *This is a central step of the procedure and needs to be correct.* The above message `Automatically inferred sample pattern: 'sample_read'` indicates that the tool recognized a file pattern, which was indeed correct. The `sample_read` pattern expects a '.fastq.gz' archive, starting with the the sample name, followed by an underscore and 'R1' or 'R2'. All files need to have the same file name structure, otherwise the `make_sample_tab` needs to be called repeatedly for each set of files with a different name structure.

If the pattern is not correctly recognized, you can specify it by yourself. This should actually only be necessary if the files don't match any pattern, or they match more than one, so the tool cannot decide which one to use. With samples from an Illumina sequencer, you can specify the 'illumina' pattern:

```sh
make_sample_tab -d read_files/run1 -f simple -s illumina
```

Patterns are defined as regular expressions in [`sample_patterns.toml`](make_sample_tab/sample_patterns.toml) (currently, there are only `sample_read` and `illumina` in this file). A custom pattern file can be supplied with `--pattern-file <file>`. Even simpler is to just supply a regular expression to `-s/--sample-pattern`:

```sh
make_sample_tab -d x -f simple -s '(.+?)_[a-z0-9]+_R([12])\.fastq\.gz'
```

This pattern is similar to the `sample_name` pattern, but there is an additional word with lowercase characters or numbers inbetween (`[a-z0-9]+?`) which is not part of the sample name. So, it would match a file name containing a hash, like `sample_name_3144c78ecad5487a026517bbfb156a9c_R1.fastq.gz`.

### Output formats

Different pipelines have different format requirements, e.g. on headers or relative vs. absolute file paths or field separators. Still, the general structure is usually the same: (1) sample id, (2) forward read path, (3) optional reverse read path. Other or column structures or additional metadata fields can currently not be handled by this tool.

A minimal list of formats is defined in [`formats.toml`](make_sample_tab/formats.toml). It is possible to define your own format list in a separate TOML file and supply it with `--format-config-file <path>`. Alternatively, the different options can be manually supplied (see `make_sample_tab --help`).

Currently, the only other format apart from the *simple* one is the [QIIME2 manifest format](https://docs.qiime2.org/2023.7/tutorials/importing/#fastq-manifest-formats). Here is an example:

```sh
make_sample_tab -d read_files/run1 -f qiime
```

`samples_run1_paired.tsv`:

```
sample-id	forward-absolute-filepath	reverse-absolute-filepath
a	$PWD/read_files/run1/a_R1.fastq.gz	$PWD/read_files/run1/a_R2.fastq.gz
b	$PWD/read_files/run1/b_R1.fastq.gz	$PWD/read_files/run1/b_R2.fastq.gz
```


### Generating sample files for multiple runs

In order to also generate a sample file for runs 2 and 3, we have several options:

#### Option 1

We can just add all paths in a space-delimited list:

```sh
make_sample_tab -d read_files/run1 read_files/run2 read_files/run3 -f simple
```

`samples_run1_paired.tsv`:

```
id	R1	R2
a	read_files/run1/a_R1.fastq.gz	read_files/run1/a_R2.fastq.gz
b	read_files/run1/b_R1.fastq.gz	read_files/run1/b_R2.fastq.gz
```


`samples_run2_paired.tsv`:

```
id	R1	R2
a	read_files/run2/a_R1.fastq.gz	read_files/run2/a_R2.fastq.gz
```

`samples_run3_single.tsv`:

```
id	R1
y	read_files/run3/y_R1.fastq.gz
x	read_files/run3/x_R1.fastq.gz
```

#### Option 2

There is a special `{run}` wildcard, which assigns the run name based on the given part of the path.

```sh
make_sample_tab -d read_files/{run} -f simple
```

```
1 samples from '2' (paired-end) written to samples_2_paired.tsv
2 samples from '1' (paired-end) written to samples_1_paired.tsv
2 samples from '3' (single-end) written to samples_3_single.tsv
```

> **_NOTE:_** In UNIX shells with globbing capabilities, there is also another way:
> ```sh
> make_sample_tab -d read_files/* -f simple
> # expanded to:
> # make_sample_tab -d read_files/run1 read_files/run2 read_files/run3 -f simple
> ```
>
> However, this only works if the directory name is the run name. The `{run}` wildcard still has its use by allowing to set the run name from a directory higher up in the hierarchy, e.g. `-d /path/to/{run}/with/nested/path/*`, or with file patterns (see below).

We can also only extract part of a directory name. Here, we only want the number after 'run':

```sh
make_sample_tab -d read_files/run{run} -f simple
```

```
1 samples from '2' (paired-end) written to samples_2_paired.tsv
2 samples from '1' (paired-end) written to samples_1_paired.tsv
2 samples from '3' (single-end) written to samples_3_single.tsv
```

#### Option 3

The arguably simplest option would be to use the `-r/--recursive` flag, if there are no other subdirectories in *read_files*, which we don't want to include:

```sh
make_sample_tab -d read_files -r -f simple
```

### Manual run names and directory merging

If the directory should not be used for setting the run name, its name can be specified manually:

```sh
make_sample_tab -d other_run=read_files/run1 -f simple
```

This generates a file called `samples_other_run_paired.tsv`. Apart from determining the run name, this feature also allows merging files from different directories into one run:

```sh
make_sample_tab -d other_run=read_files/run1 other_run=read_files/run2 -f simple
```

Unfortunately, in this case this generates a an error due to sample `a` being present both in run1 and run2:

```
Exception: Several files were found for sample 'a'. Was it sequenced in different runs or could there be a name clash? Also, check the sample pattern, did it correctly recognize the name? If so, you can either enable 'make_unique' or use the {run} wildcard to output one file per run. The problematic files:
read_files/run1/a_R1.fastq.gz, read_files/run1/a_R2.fastq.gz, read_files/run2/a_R1.fastq.gz, read_files/run2/a_R2.fastq.gz
```

This problem is also discussed below in more detail.


### Advanced selection

#### With --paired-filter

For instance, if wanting to restrict to forward reads, while omitting reverse reads, one way is to add `--paired-filter forward`:

```sh
make_sample_tab -d read_files/{run} --paired-filter forward -f simple
```

We can already see from the message, that all files are single-end (have only an R1 column).

```
1 samples from 'run2' (single-end) written to samples_run2_single.tsv
2 samples from 'run1' (single-end) written to samples_run1_single.tsv
2 samples from 'run3' (single-end) written to samples_run3_single.tsv
```

If for some reason, we want to keep only reverse reads, they will still be listed in the `R1` column.

```sh
make_sample_tab -d read_files/{run} --paired-filter reverse -f simple
```

However, the file names indicate this fact by containing `single_rev` instead of just `single`. `run3` contains only forward reads (see file structure at start of this tutorial) and is thus not returned.

```
1 samples from 'run2' (single_rev-end) written to samples_run2_single_rev.tsv
2 samples from 'run1' (single_rev-end) written to samples_run1_single_rev.tsv
```

#### Glob patterns

The even more flexible way is to use [glob patterns](https://en.wikipedia.org/wiki/Glob_(programming)) (`-p/--patterns` argument) for file selection. This will also work on Windows (but see note on quotes below).

```sh
make_sample_tab -p read_files/*/*_R1.fastq.gz -f simple
```

```
2 samples from 'run1' (single-end) written to samples_run1_single.tsv
1 samples from 'run2' (single-end) written to samples_run2_single.tsv
2 samples from 'run3' (single-end) written to samples_run3_single.tsv
```

> **_NOTE:_** In the above example there are no quotes around the pattern. However, keep in mind that **it matters whether you use *double* or *single* quotes or *no quotes* at all!**. Generally, quotes have to be added around paths and/or path patterns if there are any **spaces** paths. Recommendations:
> 
> * **Windows:** Always use *double quotes* (") or no quotes:
> ```sh
> make_sample_tab -p "read_files with spaces/*/*_R1.fastq.gz" -f simple
> ```
> * **UNIX (Bash):** Double or *no* quotes should work, but single quotes (') are to be preferred:
> ```sh
> make_sample_tab -p 'read_files with spaces/*/*_R1.fastq.gz' -f simple
> ```
> *Reason:* With single quotes, the glob pattern expansion is done entirely in by Python in the `make_sample_tab` script itself. With double quotes (") or no quotes at all the pattern is expanded in the shell and then passed to `make_sample_tab` as a (potentially very long) list of files. Fortunately, the tool is designed in a way that the outcome should be the same irrespective of whether quotes are used or not. However, without single quotes there may be problems with large numbers of files. Recursive patterns ('**') on the other hand are a bit special: they are only evaluated in Bash if the 'globstar' option is activated, otherwise the expansion is done in the Python script.

##### Recursive patterns

By adding the `-r/--recursive` flag, it is even possible to match samples in subdirectories of unknown/unlimited nesting depth with `**`:

```sh
make_sample_tab -p **/*R*.fastq.gz -f simple
```

```
1 samples from 'run2' (paired-end) written to samples_run2_paired.tsv
2 samples from 'run1' (paired-end) written to samples_run1_paired.tsv
2 samples from 'run3' (single-end) written to samples_run3_single.tsv
```

However, it is important that the pattern is restrictive enough to not match unwanted files (e.g. index files). Therefore, we inserted the '*R*' part.

## Sample table paths

By default, sample table output files have the following structure:

```
"{out_prefix}{run}_{layout}.tsv"
```

The output prefix/directory and the output file structure can be changed with `-o/--out-prefix` and/or `--path-template`, e.g.:

```sh
make_sample_tab -rd read_files -f simple \
    -o 'some_directory' --path-template '{out_prefix}/{run}/{layout}/samples.txt'
```

Now, the sample tables will be in subdirectories, nested by run and layout:

```
1 samples from 'run2' (paired-end) written to some_directory/run2/paired/samples.txt
2 samples from 'run1' (paired-end) written to some_directory/run1/paired/samples.txt
2 samples from 'run3' (single-end) written to some_directory/run3/single/samples.txt
```

## Resolving name conflicts

In some cases, the same sample may occur in different directories, e.g. because the same samples/libraries were re-sequenced, or because of name clashes. In case you want to still merge these for a common analysis, the `-u/--make-unique` flag will add numbered suffixes (`_1`, `_2`, ...) to the sample names to make them unique.

```sh
make_sample_tab -u -p 'my_run=read_files/run*/*.fastq.gz' -f simple
```

The result in this case are actually two files, one for the single-end layout files (`run3`) and one for the paired-end files (`run1`, `run2`), since layouts cannot be mixed.

```
Automatically inferred sample pattern: 'sample_read'
2 samples from 'my_run' (single-end) written to samples_my_run_single.tsv
3 samples from 'my_run' (paired-end) written to samples_my_run_paired.tsv
```

`samples_my_run_paired.tsv`:

```
id	R1	R2
a_1	read_files/run1/a_R1.fastq.gz	read_files/run1/a_R2.fastq.gz
a_2	read_files/run2/a_R1.fastq.gz	read_files/run2/a_R2.fastq.gz
b	read_files/run1/b_R1.fastq.gz	read_files/run1/b_R2.fastq.gz
```

The sample `a` has been de-duplicated.


> **_NOTE:_** Sample name clashes within **the same directory** are not allowed by this tool. It is based on the concept of sequencing runs, and usually files from one run are in the same directory, and duplicates should never occur within the same run. 
