import unittest
from pipeline_runtime.paths import ContainerPathError, map_host_path, map_staged_inputs


class ContainerPathMappingTests(unittest.TestCase):
	def setUp(self):
		self.workspace = '/cluster/jobs/alice/job_123'
		self.binds = [
			{'source': '/cluster/jobs', 'destination': '/container/jobs'},
			{'source': self.workspace, 'destination': '/work/job_123'},
		]

	def test_workspace_exact(self):
		self.assertEqual(map_host_path(self.workspace, self.workspace, self.binds), '/work/job_123')

	def test_nested_staged_file(self):
		self.assertEqual(map_host_path(self.workspace + '/input/obs.ms/table.dat', self.workspace, self.binds), '/work/job_123/input/obs.ms/table.dat')

	def test_multiple_inputs(self):
		paths = {'image': self.workspace + '/input/image.fits', 'table': self.workspace + '/input/table'}
		self.assertEqual(map_staged_inputs(paths, self.workspace, self.binds), {'image': '/work/job_123/input/image.fits', 'table': '/work/job_123/input/table'})

	def test_identity_bind(self):
		binds = [{'source': self.workspace, 'destination': self.workspace}]
		self.assertEqual(map_host_path(self.workspace + '/input/a', self.workspace, binds), self.workspace + '/input/a')

	def test_reject_other_user_and_prefix_collision(self):
		for path in ('/cluster/jobs/bob/job/input/a', self.workspace + '_evil/input/a'):
			with self.assertRaises(ContainerPathError):
				map_host_path(path, self.workspace, self.binds)

	def test_reject_traversal(self):
		for path in (self.workspace + '/input/../secret', self.workspace + '//input/a', self.workspace + '/./input/a'):
			with self.assertRaises(ContainerPathError):
				map_host_path(path, self.workspace, self.binds)

	def test_no_mount(self):
		with self.assertRaises(ContainerPathError):
			map_host_path(self.workspace + '/input/a', self.workspace, [{'source': '/elsewhere', 'destination': '/x'}])

	def test_reject_duplicate_mount(self):
		with self.assertRaises(ContainerPathError):
			map_host_path(self.workspace + '/input/a', self.workspace, self.binds + [self.binds[1]])

	def test_reject_nested_redirect_outside_workspace(self):
		binds = self.binds + [{'source': self.workspace + '/input', 'destination': '/untrusted'}]
		with self.assertRaises(ContainerPathError):
			map_host_path(self.workspace + '/input/a', self.workspace, binds)

	def test_reject_relative_and_bad_mount(self):
		with self.assertRaises(ContainerPathError):
			map_host_path('input/a', self.workspace, self.binds)
		with self.assertRaises(ContainerPathError):
			map_host_path(self.workspace + '/input/a', self.workspace, [{'source': '/cluster/jobs', 'destination': 'relative'}])


if __name__ == '__main__':
	unittest.main()
