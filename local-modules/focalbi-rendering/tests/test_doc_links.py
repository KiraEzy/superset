# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
"""Documentation removal preserves user text and refuses changed owned blocks."""

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from doc_links import block, owned_path, remove_blocks


class DocumentOwnership(unittest.TestCase):
    """Verify uninstall edits only unchanged module-owned documentation."""

    def test_remove_preserves_unowned_content(self) -> None:
        """Retain surrounding user documentation and reject escaping paths."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "README.md"
            content = (
                "User setup\n<!-- focalbi.rendering:begin -->\n"
                "[module](module/README.md)\n"
                "<!-- focalbi.rendering:end -->\nUser notes\n"
            )
            path.write_text(content)
            records = [
                {
                    "path": "README.md",
                    "sha256": hashlib.sha256(block(content).encode()).hexdigest(),
                }
            ]
            remove_blocks(root, records)
            assert path.read_text() == "User setup\n\nUser notes\n"
            with self.assertRaises(ValueError):
                owned_path(root, "../outside.md")

    def test_changed_block_refusal_is_atomic(self) -> None:
        """Reject all documentation removal when any owned block changed."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            content = (
                "{/* focalbi.rendering:begin */}Module guide"
                "{/* focalbi.rendering:end */}"
            )
            records = []
            for name in ["first.mdx", "second.mdx"]:
                (root / name).write_text(content)
                records.append(
                    {
                        "path": name,
                        "sha256": hashlib.sha256(block(content).encode()).hexdigest(),
                    }
                )
            (root / "second.mdx").write_text(
                content.replace("Module guide", "User changed guide")
            )
            with self.assertRaises(ValueError):
                remove_blocks(root, records)
            assert (root / "first.mdx").read_text() == content


if __name__ == "__main__":
    unittest.main()
