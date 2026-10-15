"""Execute only the ARG validation shell line, never Docker/build/image code."""
import os
from pathlib import Path
import subprocess
import sys
import unittest


class DockerfileArgumentTests(unittest.TestCase):
    def test_both_images_validate_quoted_argument_without_environment_lookup(self):
        root = Path(__file__).resolve().parents[1]
        for image in ('runner','target'):
            source = (root/'images'/image/'Dockerfile').read_text()
            command = next(line[4:] for line in source.splitlines() if line.startswith('RUN python -c'))
            self.assertIn('sys.argv[1]',command)
            self.assertIn('"$PYTHON_BASE"',command)
            self.assertNotIn('os.environ',command)
            for value,valid in [('python:3.13-slim@sha256:'+'a'*64,True),
                                ('',False),('python:latest',False),('python@sha256:short',False),
                                ('python\n@sha256:'+'a'*64,False),('$(exit 0)',False)]:
                with self.subTest(image=image,value=value):
                    env = {**os.environ,'PYTHON_BASE':value,'PYTHONOPTIMIZE':'1',
                           'PATH':str(Path(sys.executable).parent)+os.pathsep+os.environ.get('PATH','')}
                    result = subprocess.run(['/bin/sh','-c',command],env=env,capture_output=True,timeout=5)
                    self.assertEqual(result.returncode == 0,valid,result.stderr.decode())
