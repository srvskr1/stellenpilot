import io
import os
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from stellenpilot import builtin


class AssetTest(unittest.TestCase):
    def test_one_cpu_build_per_platform(self):
        b = builtin.LLAMA_BUILD
        self.assertEqual(builtin.engine_asset("Windows", "AMD64"), f"llama-{b}-bin-win-cpu-x64.zip")
        self.assertEqual(builtin.engine_asset("Windows", "ARM64"), f"llama-{b}-bin-win-cpu-arm64.zip")
        self.assertEqual(builtin.engine_asset("Darwin", "arm64"), f"llama-{b}-bin-macos-arm64.tar.gz")
        self.assertEqual(builtin.engine_asset("Darwin", "x86_64"), f"llama-{b}-bin-macos-x64.tar.gz")
        self.assertEqual(builtin.engine_asset("Linux", "x86_64"), f"llama-{b}-bin-ubuntu-x64.tar.gz")
        self.assertEqual(builtin.engine_asset("Linux", "aarch64"), f"llama-{b}-bin-ubuntu-arm64.tar.gz")
        self.assertIsNone(builtin.engine_asset("Linux", "i686"))
        self.assertIsNone(builtin.engine_asset("FreeBSD", "x86_64"))


class ExtractTest(unittest.TestCase):
    def test_finds_server_in_nested_folder_and_blocks_escapes(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"STELLENPILOT_AI_DIR": d}):
            name = "llama-server.exe" if os.name == "nt" else "llama-server"
            arc = Path(d) / "e.tar.gz"
            with tarfile.open(arc, "w:gz") as t:
                for n in (f"llama-b1/{name}", "llama-b1/libllama.so"):
                    data = b"x"
                    info = tarfile.TarInfo(n)
                    info.size = len(data)
                    t.addfile(info, io.BytesIO(data))
            builtin._safe_extract(arc, Path(d) / "engine")
            self.assertEqual(builtin.engine_path().name, name)
            bad = Path(d) / "bad.zip"
            with zipfile.ZipFile(bad, "w") as z:
                z.writestr("../evil.txt", "x")
            with self.assertRaises(OSError):
                builtin._safe_extract(bad, Path(d) / "engine2")
            self.assertFalse((Path(d) / "evil.txt").exists())

    def test_status_without_files(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"STELLENPILOT_AI_DIR": d}):
            st = builtin.status("light")
            self.assertFalse(st["ready"])
            self.assertEqual(st["model"], "light")
            self.assertEqual(set(st["models"]), {"standard", "light"})
            with self.assertRaises(RuntimeError):
                builtin.ensure_running("light")


class LimitTest(unittest.TestCase):
    def test_local_models_read_twenty_jobs_cloud_all(self):
        from stellenpilot.llm import LLM

        class S(dict):
            def secret(self, k):
                return "k"
        base = {"timeout": 1}
        self.assertEqual(LLM(S(llm={**base, "provider": "builtin"})).ai_job_limit, 20)
        self.assertEqual(LLM(S(llm={**base, "provider": "builtin"})).model, "standard")
        self.assertEqual(LLM(S(llm={**base, "provider": "anthropic"})).ai_job_limit, 0)
        self.assertEqual(LLM(S(llm={**base, "provider": "ollama", "model": "m", "max_ai_jobs": 5})).ai_job_limit, 5)


if __name__ == "__main__":
    unittest.main()


class PipelineCapTest(unittest.TestCase):
    def test_ai_reads_only_the_most_promising_jobs(self):
        import shutil
        from stellenpilot import pipeline
        from stellenpilot.config import Settings
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            ex = Path(pipeline.__file__).parent / "examples"
            shutil.copy(ex / "profile.example.toml", home / "profile.toml")
            (home / "config.toml").write_text('[llm]\nprovider = "builtin"\nmax_ai_jobs = 2\n[gmail]\nenabled = false\n', encoding="utf-8")
            settings = Settings(home)
            jobs = [{"id": f"j{i}", "title": t, "company": f"C{i}", "location": "Essen", "url": "", "source": "x",
                     "description": "Python SQL AWS" if i < 2 else "Forklift driver", "dedupe_key": f"k{i}"}
                    for i, t in enumerate(["Data Engineer", "Data Analyst", "Driver", "Cook", "Cashier"])]
            used = []

            def fake_score(job, profile, llm=None, *a):
                used.append((job["id"], bool(llm)))
                return {"match": 50, "fit": "", "why": "", "gaps": "", "gap_tags": [], "lang": "English", "german_level": "", "summary_en": ""}
            with mock.patch.object(pipeline, "collect", return_value=(jobs, [])), \
                 mock.patch.object(pipeline, "score_job", side_effect=fake_score), \
                 mock.patch.object(pipeline, "check_closed", return_value=0):
                pipeline.run(settings, tailor=False)
            self.assertEqual({j for j, ai in used if ai}, {"j0", "j1"})
            self.assertEqual(len(used), 5)
