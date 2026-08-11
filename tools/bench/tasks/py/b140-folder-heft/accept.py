from solution import file_paths, heavy_folders, tree_bytes

tree = {
    "name": "media",
    "children": [
        {
            "name": "clips",
            "children": [
                {"name": "intro.mov", "bytes": 400},
                {"name": "raw", "children": [{"name": "take1.mov", "bytes": 3000}]},
            ],
        },
        {"name": "notes.txt", "bytes": 50},
        {"name": "empty", "children": []},
    ],
}

assert heavy_folders(tree, 3000) == [
    ["media", 3450],
    ["media/clips", 3400],
    ["media/clips/raw", 3000],
], "folders at or above the threshold, in walking order"
assert heavy_folders(tree, 3001) == [
    ["media", 3450],
    ["media/clips", 3400],
], "a folder exactly one byte short drops out"
assert heavy_folders(tree, 0) == [
    ["media", 3450],
    ["media/clips", 3400],
    ["media/clips/raw", 3000],
    ["media/empty", 0],
], "threshold zero reports every folder, empty ones included"
assert heavy_folders({"name": "solo.txt", "bytes": 5}, 0) == [], "a file root has no folders"
assert file_paths(tree) == [
    "media/clips/intro.mov",
    "media/clips/raw/take1.mov",
    "media/notes.txt",
], "file paths in walking order"
assert file_paths({"name": "solo.txt", "bytes": 5}) == ["solo.txt"], "a file root is its own path"
assert tree_bytes(tree) == 3450, "bytes roll up through every folder"
assert tree_bytes({"name": "empty", "children": []}) == 0, "an empty folder holds zero bytes"


def rejects(fn, *args):
    try:
        fn(*args)
    except Exception:
        return True
    return False


assert rejects(heavy_folders, 42, 0), "non-mapping node rejected"
assert rejects(heavy_folders, {"name": "", "children": []}, 0), "empty name rejected"
assert rejects(heavy_folders, {"name": "a/b", "children": []}, 0), "slash in a name rejected"
assert rejects(heavy_folders, {"name": "x"}, 0), "neither bytes nor children rejected"
assert rejects(
    heavy_folders, {"name": "x", "bytes": 5, "children": []}, 0
), "both bytes and children rejected"
assert rejects(heavy_folders, tree, -1), "negative threshold rejected"
assert rejects(heavy_folders, tree, 2.5), "fractional threshold rejected"
assert rejects(file_paths, {"name": "x", "children": "nope"}), "non-list children rejected"
assert rejects(tree_bytes, {"name": "x", "bytes": 1.5}), "fractional bytes rejected"
print("ok")
