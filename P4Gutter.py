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
        out, err = shell_run([P4['binary'], 'diff', self.view.file_name()], environment)
        if len(err) and not len(out):
            if P4['errorlog']:
                print('P4Gutter Error: "{}".'.format(err[:-1]).replace('\r', '').replace('\n', ' > '))
            return [], [], [], []

        additions, deletions_above, deletions_below, modifications = [], [], [], []
        diff_type, diff_begin, diff_end = None, 1, 1
        lines = out.split('\n')
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
