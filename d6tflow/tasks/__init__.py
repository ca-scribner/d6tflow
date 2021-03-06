import luigi
import luigi.tools.deps
import collections

import d6tcollect

import d6tflow.targets
import d6tflow.settings as settings
from d6tflow.cache import data as cache
import d6tflow.cache

def _taskpipeoperation(task, fun, funargs=None):
    pipe = task.get_pipe()
    fun = getattr(pipe, fun)
    funargs = {} if funargs is None else funargs
    return fun(**funargs)

class TaskData(luigi.Task):
    """
    Task which has data as input and output

    Args:
        target_class (obj): target data format
        target_ext (str): file extension
        persist (list): list of string to identify data
        data (dict): data container for all outputs

    """
    target_class = d6tflow.targets.DataTarget
    target_ext = 'ext'
    persist = ['data']

    def invalidate(self, confirm=True):
        """
        Invalidate a task, eg by deleting output file
        """
        if confirm:
            c = input('Confirm invalidating task: {} (y/n)'.format(self.__class__.__qualname__))
        else:
            c = 'y'
        if c=='y' and self.complete():
            if self.persist == ['data']:  # 1 data shortcut
                self.output().invalidate()
            else:
                [t.invalidate() for t in self.output().values()]
        return True

    @d6tcollect._collectClass
    def complete(self, cascade=True):
        """
        Invalidate a task, eg by deleting output file
        """
        complete = super().complete()
        if d6tflow.settings.check_dependencies and cascade and not getattr(self, 'external', False):
            complete = complete and all([t.complete() for t in luigi.task.flatten(self.requires())])
        return complete

    def _getpath(self, dirpath, k, subdir=True):
        tidroot = getattr(self, 'target_dir', self.task_id.split('_')[0])
        fname = '{}-{}'.format(self.task_id, k) if (settings.save_with_param and getattr(self, 'save_attrib', True)) else '{}'.format(k)
        fname += '.{}'.format(self.target_ext)
        if subdir:
            path = dirpath / tidroot / fname
        else:
            path = dirpath / fname
        return path

    def output(self):
        """
        Similar to luigi task output
        """

        # output dir, check if using d6tpipe
        if hasattr(self, 'pipename'):
            import d6tflow.pipes
            dirpath = d6tflow.pipes.get_dirpath(self.pipename)
        else:
            dirpath = settings.dirpath

        save_ = getattr(self, 'persist', [])
        output = dict([(k, self.target_class(self._getpath(dirpath, k))) for k in save_])
        if self.persist==['data']: # 1 data shortcut
            output = output['data']
        return output

    def inputLoad(self, keys=None, task=None, cached=False):
        """
        Load all or several outputs from task

        Args:
            keys (list): list of data to load
            task (str): if requires multiple tasks load that task 'input1' for eg `def requires: {'input1':Task1(), 'input2':Task2()}`
            cached (bool): cache data in memory

        Returns: list or dict of all task output
        """
        if isinstance(self.requires(), dict) and task is not None:
            input = self.input()[task]
        else:
            input = self.input()

        data = _inputLoad(keys=keys, input=input, cached=cached)
        return data

    def outputLoad(self, keys=None, as_dict=False, cached=False):
        """
        Load all or several outputs from task

        Args:
            keys (list): list of data to load
            as_dict (bool): cache data in memory
            cached (bool): cache data in memory

        Returns: list or dict of all task output
        """
        if not self.complete():
            raise RuntimeError('Cannot load, task not complete, run flow first')
        keys = self.persist if keys is None else keys
        if self.persist==['data']: # 1 data shortcut
            return self.output().load()

        data = {k: v.load(cached) for k, v in self.output().items() if k in keys}
        if not as_dict:
            data = list(data.values())
        return data

    def save(self, data, **kwargs):
        """
        Persist data to target

        Args:
            data (dict): data to save. keys are the self.persist keys and values is data

        """
        if self.persist==['data']: # 1 data shortcut
            self.output().save(data, **kwargs)
        else:
            targets = self.output()
            if not set(data.keys())==set(targets.keys()):
                raise ValueError('Save dictionary needs to consistent with Task.persist')
            for k, v in data.items():
                targets[k].save(v, **kwargs)

    @d6tcollect._collectClass
    def get_pipename(self):
        """
        Get associated pipe name
        """
        return getattr(self, 'pipename', d6tflow.cache.pipe_default_name)
    def get_pipe(self):
        """
        Get associated pipe object
        """
        import d6tflow.pipes
        return d6tflow.pipes.get_pipe(self.get_pipename())
    def pull(self, **kwargs):
        """
        Pull files from data repo
        """
        return _taskpipeoperation(self,'pull', **kwargs)
    def pull_preview(self, **kwargs):
        """
        Preview pull files from data repo
        """
        return _taskpipeoperation(self,'pull_preview', **kwargs)
    def push(self, **kwargs):
        """
        Push files to data repo
        """
        return _taskpipeoperation(self,'push', **kwargs)
    def push_preview(self, **kwargs):
        """
        Preview push files to data repo
        """
        return _taskpipeoperation(self,'push_preview', **kwargs)


def is_iterable(arg):
    """
    Returns whether an argument is an iterable but not a string
    From stackoverflow: "how to tell a varaiable is iterable but not a string"
    Args:
        arg: some variable to be tested
    Returns:
        (bool)
    """
    return (
            isinstance(arg, collections.Iterable)
            and not isinstance(arg, str)
    )


def make_iterable(arg):
    """
    Makes arg into an iterable if it isn't already (note that strings are ignored and treated as non-iterable)
    """
    return arg if is_iterable(arg) else (arg,)


def _inputLoad(keys=None, input=None, cached=False):
    if isinstance(input, tuple):
        data = []
        for o in input:
            data.extend(make_iterable(_inputLoad(keys=None, input=o, cached=cached)))
    elif isinstance(input, dict):
        # TODO: This doesn't work recursively like the other part
        keys = input.keys() if keys is None else keys
        data = {k: v.load(cached) for k, v in input.items() if k in keys}
        # TODO: Why flatten the structure of the input we've been given?  We could leave it nested same as output 
        #  dict.  This sort of implies we're not really keywording for our interface, just for putting it to disk
        data = list(data.values())
    else:
        data = input.load()
    return data



class TaskCache(TaskData):
    """
    Task which saves to cache
    """
    target_class = d6tflow.targets.CacheTarget
    target_ext = 'cache'

class TaskCachePandas(TaskData):
    """
    Task which saves to cache pandas dataframes
    """
    target_class = d6tflow.targets.PdCacheTarget
    target_ext = 'cache'

class TaskJson(TaskData):
    """
    Task which saves to json
    """
    target_class = d6tflow.targets.JsonTarget
    target_ext = 'json'

class TaskPickle(TaskData):
    """
    Task which saves to pickle
    """
    target_class = d6tflow.targets.PickleTarget
    target_ext = 'pkl'

class TaskCSVPandas(TaskData):
    """
    Task which saves to CSV
    """
    target_class = d6tflow.targets.CSVPandasTarget
    target_ext = 'csv'

class TaskCSVGZPandas(TaskData):
    """
    Task which saves to CSV
    """
    target_class = d6tflow.targets.CSVGZPandasTarget
    target_ext = 'csv.gz'

class TaskExcelPandas(TaskData):
    """
    Task which saves to CSV
    """
    target_class = d6tflow.targets.ExcelPandasTarget
    target_ext = 'xlsx'

class TaskPqPandas(TaskData):
    """
    Task which saves to parquet
    """
    target_class = d6tflow.targets.PqPandasTarget
    target_ext = 'parquet'

class TaskAggregator(luigi.Task):
    """
    Task which yields other tasks

    NB: Use this function by implementing `run()` which should do nothing but yield other tasks

    example::

        class TaskCollector(d6tflow.tasks.TaskAggregator):
            def run(self):
                yield Task1()
                yield Task2()

    """

    def invalidate(self, confirm=True):
        [t.invalidate(confirm) for t in self.run()]

    def complete(self, cascade=True):
        return all([t.complete(cascade) for t in self.run()])

    def output(self):
        return [t.output() for t in self.run()]

    def outputLoad(self, keys=None, as_dict=False, cached=False):
        return [t.outputLoad(keys,as_dict,cached) for t in self.run()]

class TaskMatplotlib(TaskData):
    """
    Task which saves plots to png, does not load
    """
    target_class = d6tflow.targets.MatplotlibTarget
    target_ext = 'png'
