import os
import re
import subprocess
import sublime
import sublime_plugin

# GLOBALS --------------------------------------------------------------------------------------------------------------------------
P4_WORKSPACE = '.p4_workspace'
P4 = {}
P4_DIFF_HEADER = re.compile('^([0-9,]+)([cad])([0-9,]+)$')


# UTILITIES ------------------------------------------------------------------------------------------------------------------------
def path_is_root(path):
    if not os.path.isdir(path):
        return False
    return os.path.realpath(path) == os.path.realpath(os.path.join(path, '..'))


def shell_run(args, env=None):
    startupinfo = None
    if os.name == 'nt':
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    process = subprocess.Popen(args, stdout=subprocess.PIPE, startupinfo=startupinfo, stderr=subprocess.PIPE, env=env)
    return process.stdout.read().decode(encoding='UTF-8'), process.stderr.read().decode(encoding='UTF-8')


def p4_find_workspace(file_path):
    parent, _ = os.path.split(file_path)
    while 1:
        test_path = os.path.join(parent, P4_WORKSPACE)
        if os.path.isfile(test_path):
            with open(test_path, 'r') as fin:
                workspace = fin.read().replace('\r', '').replace('\n', '')
            return workspace
        if path_is_root(parent):
            return None
        parent, _ = os.path.split(parent)


def st3_region_for_line(view, line_number):
    return view.line(view.text_point(line_number - 1, 0))


def st3_view_on_disk(view):
    return view.file_name() is not None


# EVENT LISTENER -------------------------------------------------------------------------------------------------------------------
class P4GutterEventListener(sublime_plugin.EventListener):
    def on_load_async(self, view):
        if st3_view_on_disk(view) and ('binary' in P4) and P4['binary']:
            view.window().run_command('p4_gutter_diff')

    def on_post_save_async(self, view):
        if st3_view_on_disk(view) and ('binary' in P4) and P4['binary']:
            view.window().run_command('p4_gutter_diff')


# ANNOTATION -----------------------------------------------------------------------------------------------------------------------
class P4AnnotationCommand(sublime_plugin.WindowCommand):
    def run(self):
        print('P4Annotation')
        self.view = self.window.active_view()
        if not self.view:
            sublime.set_timeout(self.run, 1)
            return
        workspace = p4_find_workspace(self.view.file_name()) or P4['workspace']
        if not workspace:
            return

        annotation = self.annotate(workspace)
        if not annotation:
            return

        anno_view = self.window.new_file()
        _, base = os.path.split(self.view.file_name())
        anno_view.set_name('ANNOTATE: ' + base)
        anno_view.set_scratch(True)
        anno_view.settings().set('p4_annotation', annotation)
        anno_view.run_command('p4_annotation_populate')

    def annotate(self, workspace):
        environment = os.environ
        environment['P4PORT'] = P4['port']
        environment['P4USER'] = P4['user']
        environment['P4CLIENT'] = workspace

        annotation, change_lists = self.annotate_sub_1(environment)
        if not annotation:
            return ''

        annotation = self.annotate_sub_2(environment, annotation, change_lists)
        if not annotation:
            return ''

        return annotation

    def annotate_sub_1(self, environment):
        output, error = shell_run([P4['binary'], 'annotate', '-q', '-c', self.view.file_name()], environment)
        if len(error) and not len(output):
            return None, None
        output = output.replace('\r', '')  # replace CRs

        # get all referenced CL numbers
        cl_unique = {}
        cl_pattern = re.compile('^([0-9]+):', re.MULTILINE)
        for cl_match in cl_pattern.finditer(output):
            cl_number = cl_match.group(1)
            if cl_number not in cl_unique:
                cl_unique[cl_number] = ''

        return output, cl_unique


    def annotate_sub_2(self, environment, annotation, change_lists):
        # find CL owners
        who_pattern = re.compile('^Change [0-9]+ by ([^@]+)@')
        max_len_number, max_len_name = 0, 0
        for cl_number in change_lists.keys():
            if len(cl_number) > max_len_number:
                max_len_number = len(cl_number)
            output, error = shell_run([P4['binary'], 'describe', '-s', cl_number], environment)
            if len(error) and not len(output):
                continue
            who_match = who_pattern.search(output)
            if not who_match:
                continue
            who_name = who_match.group(1)
            if len(who_name) > max_len_name:
                max_len_name = len(who_name)
            change_lists[cl_number] = who_name

        for cl_number in change_lists.keys():
            pad_number = cl_number.ljust(max_len_number, ' ')
            pad_name = change_lists[cl_number].ljust(max_len_name, ' ')
            replacer = re.compile('^' + cl_number + ':', re.MULTILINE)
            annotation = re.sub(replacer, pad_number + ' ' + pad_name + ' |', annotation)

        return annotation


class P4AnnotationPopulate(sublime_plugin.TextCommand):
    def run(self, edit):
        self.view.insert(edit, 0, self.view.settings().get('p4_annotation'))
        self.view.settings().set('p4_annotation', None)


# DIFF VIEW ------------------------------------------------------------------------------------------------------------------------
class P4GutterDiffCommand(sublime_plugin.WindowCommand):
    def run(self):
        self.view = self.window.active_view()
        if not self.view:
            sublime.set_timeout(self.run, 1)
            return
        workspace = p4_find_workspace(self.view.file_name()) or P4['workspace']
        if not workspace:
            return
        additions, deletions_above, deletions_below, modifications = self.run_diff(workspace)
        self.view.add_regions('p4gutter_addition', additions, 'markup.inserted',
                              'Packages/P4Gutter/icons/addition.png', sublime.DRAW_NO_FILL | sublime.DRAW_NO_OUTLINE)
        self.view.add_regions('p4gutter_deletion_above', deletions_above, 'markup.deleted',
                              'Packages/P4Gutter/icons/deletion_above.png', sublime.DRAW_NO_FILL | sublime.DRAW_NO_OUTLINE)
        self.view.add_regions('p4gutter_deletion_below', deletions_below, 'markup.deleted',
                              'Packages/P4Gutter/icons/deletion_below.png', sublime.DRAW_NO_FILL | sublime.DRAW_NO_OUTLINE)
        self.view.add_regions('p4gutter_modification', modifications, 'markup.changed',
                              'Packages/P4Gutter/icons/modification.png', sublime.DRAW_NO_FILL | sublime.DRAW_NO_OUTLINE)

    def run_diff(self, workspace):
        environment = os.environ
        environment['P4PORT'] = P4['port']
        environment['P4USER'] = P4['user']
        environment['P4CLIENT'] = workspace
        out, err = shell_run([P4['binary'], 'diff', '-dl', self.view.file_name()], environment)
        if len(err) and not len(out):
            if P4['errorlog']:
                print('P4Gutter Error: "{}".'.format(err[:-1]).replace('\r', '').replace('\n', ' > '))
            return [], [], [], []

        additions, deletions_above, deletions_below, modifications = [], [], [], []
        diff_type, diff_begin, diff_end = None, 1, 1
        lines = out.replace('\r', '').split('\n')
        for line in lines:
            header = P4_DIFF_HEADER.match(line)
            if not header:
                continue
            diff_type, diff_begin = header.group(2), header.group(3)
            comma = diff_begin.find(',')
            if comma > -1:
                diff_end = diff_begin[comma+1:]
                diff_begin = diff_begin[0:comma]
            else:
                diff_end = diff_begin
            diff_begin, diff_end = int(diff_begin), int(diff_end)

            if diff_type == 'c':
                for index in range(diff_begin, diff_end + 1):
                    modifications.append(st3_region_for_line(self.view, index))
            elif diff_type == 'a':
                for index in range(diff_begin, diff_end + 1):
                    additions.append(st3_region_for_line(self.view, index))
            elif diff_type == 'd':
                deletions_above.append(st3_region_for_line(self.view, diff_begin))
                deletions_below.append(st3_region_for_line(self.view, diff_begin + 1))
        return additions, deletions_above, deletions_below, modifications


# SETTINGS -------------------------------------------------------------------------------------------------------------------------
def p4gutter_reload_settings():
    P4['workspace'] = P4['settings'].get('workspace')
    P4['binary'] = P4['settings'].get('binary') or 'p4'
    P4['user'] = P4['settings'].get('user')
    P4['port'] = P4['settings'].get('port')
    P4['errorlog'] = P4['settings'].get('errorlog')


# PLUGIN ---------------------------------------------------------------------------------------------------------------------------
def plugin_loaded():
    P4['settings'] = sublime.load_settings('P4Gutter.sublime-settings')
    P4['settings'].add_on_change('p4gutter-reload', p4gutter_reload_settings)
    p4gutter_reload_settings()
