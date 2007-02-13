from rope.base import codeanalyze, pyobjects, exceptions, change
from rope.refactor import sourceutils, functionutils, occurrences, rename


class MethodObject(object):

    def __init__(self, project, resource, offset):
        self.pycore = project.pycore
        pyname = codeanalyze.get_pyname_at(self.pycore, resource, offset)
        if pyname is None or not isinstance(pyname.get_object(),
                                            pyobjects.PyFunction):
            raise exceptions.RefactoringError(
                'Replace method with method object refactoring should be '
                'performed on a function.')
        self.pyfunction = pyname.get_object()
        self.pymodule = self.pyfunction.get_module()
        self.resource = self.pymodule.get_resource()

    def get_new_class(self, name):
        body = sourceutils.fix_indentation(self._get_body(), 8)
        return 'class %s(object):\n\n%s    def __call__(self):\n%s' % \
               (name, self._get_init(), body)

    def get_changes(self, new_class_name):
        collector = sourceutils.ChangeCollector(self.pymodule.source_code)
        start, end = self._get_body_region()
        indents = sourceutils.get_indents(
            self.pymodule.lines, self.pyfunction.get_scope().get_start()) + 4
        new_contents = ' ' * indents + 'return %s(%s)()\n' % \
                       (new_class_name, ', '.join(self._get_parameter_names()))
        collector.add_change(start, end, new_contents)
        insertion = self._get_class_insertion_point()
        collector.add_change(insertion, insertion,
                             '\n\n' + self.get_new_class(new_class_name))
        changes = change.ChangeSet('Replace method with method object refactoring')
        changes.add_change(change.ChangeContents(self.resource,
                                                 collector.get_changed()))
        return changes

    def _get_class_insertion_point(self):
        current = self.pyfunction
        while current.parent != self.pymodule:
            current = current.parent
        end = self.pymodule.lines.get_line_end(current.get_scope().get_end())
        return min(end + 1, len(self.pymodule.source_code))

    def _get_body(self):
        body = self._get_unchanged_body()
        for param in self._get_parameter_names():
            body = param + ' = 1\n' + body
            pymod = self.pycore.get_string_module(body, self.resource)
            pyname = pymod.get_attribute(param)
            finder = occurrences.FilteredOccurrenceFinder(
                self.pycore, param, [pyname])
            result = rename.rename_in_module(finder, 'self.' + param,
                                             pymodule=pymod)
            body = result[result.index('\n') + 1:]
        return body

    def _get_unchanged_body(self):
        start, end = self._get_body_region()
        return sourceutils.fix_indentation(
            self.pymodule.source_code[start:end], 0)

    def _get_body_region(self):
        scope = self.pyfunction.get_scope()
        lines = self.pymodule.lines
        logical_lines = codeanalyze.LogicalLineFinder(lines)
        start_line = logical_lines.get_logical_line_in(scope.get_start())[1] + 1
        start = lines.get_line_start(start_line)
        end = min(lines.get_line_end(scope.get_end()) + 1,
                  len(self.pymodule.source_code))
        return start, end

    def _get_init(self):
        params = self._get_parameter_names()
        if not params:
            return ''
        header = '    def __init__(self'
        body = ''
        for arg in params:
            new_name = arg
            if arg == 'self':
                new_name = 'host'
            header += ', %s' % new_name
            body += '        self.%s = %s\n' % (arg, new_name)
        header += '):'
        return '%s\n%s\n' % (header, body)

    def _get_parameter_names(self):
        info = functionutils.DefinitionInfo.read(self.pyfunction)
        result = []
        for arg, default in info.args_with_defaults:
            result.append(arg)
        if info.args_arg:
            result.append(info.args_arg)
        if info.keywords_arg:
            result.append(info.keywords_arg)
        return result
