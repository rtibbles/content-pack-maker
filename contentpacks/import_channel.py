import os
import json
import hashlib
import shutil
import copy
import zipfile
from slugify import slugify
import logging
from contentpacks.utils import extract_and_cache_file

slug_key = {
    "Topic": "slug",
    "Video": "slug",
    "Exercise": "slug",
    "AssessmentItem": "slug",
    "Document": "slug",
    "Audio": "slug",
}

title_key = {
    "Topic": "title",
    "Video": "title",
    "Exercise": "title",
    "AssessmentItem": "title",
    "Document": "slug",
}

id_key = {
    "Topic": "id",
    "Video": "id",
    "Exercise": "id",
    "AssessmentItem": "id",
    "Document": "id",
}

iconfilepath = "/images/power-mode/badges/"
iconextension = "-40x40.png"
defaulticon = "default"

file_kind_dictionary = {
    "Video": ["mp4", "mov", "3gp", "amv", "asf", "asx", "avi", "mpg", "swf", "wmv"],
    "Image": ["tif", "bmp", "png", "jpg", "jpeg"],
    "Presentation": ["ppt", "pptx"],
    "Spreadsheet": ["xls", "xlsx"],
    "Code": ["html", "js", "css", "py"],
    "Audio": ["mp3", "wma", "wav", "mid", "ogg"],
    "Document": ["pdf", "txt", "rtf", "html", "xml", "doc", "qxd", "docx"],
    "Archive": ["zip", "bzip2", "cab", "gzip", "mar", "tar"],
    "Exercise": ["exercise"],
}

file_kind_map = {}

for key, value in file_kind_dictionary.items():
    for extension in value:
        file_kind_map[extension] = key

file_meta_data_map = {
    "duration": lambda x: getattr(x, "length", None),
    "video_codec": lambda x: getattr(x, "video", [{}])[0].get("codec"),
    "audio_codec": lambda x: getattr(x, "audio", [{}])[0].get("codec"),
    "title": lambda x: getattr(x, "title", None),
    "language": lambda x: getattr(x, "langcode", None),
    "keywords": lambda x: getattr(x, "keywords", None),
    "license": lambda x: getattr(x, "copyright", None),
    "codec": lambda x: getattr(x, "codec", None),
}


def file_md5(namespace, file_path):
    m = hashlib.md5()
    m.update(namespace.encode("UTF-8"))
    with open(file_path, "r", errors='ignore') as f:
        while True:
            chunk = f.read(128)
            if not chunk:
                break
            m.update(chunk.encode("UTF-8"))
    return m.hexdigest()


def construct_node(location, parent_path, node_cache, channel, sort_order=0.0):
    """Return list of dictionaries of subdirectories and/or files in the location"""
    # Recursively add all subdirectories
    children = []
    location = location if not location or location[-1] != "/" else location[:-1]
    base_name = os.path.basename(location)
    if base_name.endswith(".json"):
        return None, sort_order
    if not parent_path:
        base_name = channel
    slug = slugify((".".join(base_name.split(".")[:-1])).encode("UTF-8"))
    if not slug or slug in node_cache["Slugs"]:
        slug = slugify(base_name.encode("UTF-8"))
    # Note: It is assumed that any file with *exactly* the same file name is the same file.
    node_cache["Slugs"].add(slug)
    current_path = os.path.join(parent_path, slug) + "/"
    try:
        with open(location + ".json", "r") as f:
            meta_data = json.load(f)
    except IOError:
        meta_data = {}
        logging.warning("No metadata for file {base_name}".format(base_name=base_name))
    node = {
        "path": current_path,
        "slug": slug,
        "sort_order": sort_order
    }
    kind = None
    assessment_items = []

    if os.path.isdir(location):
        node.update({
            "kind": "Topic",
            # Hardcode id for root node as "root"
            "id": slug if parent_path else "root",
        })

        node.update(meta_data)

        # Finally, can add contains
        contains = set([])
        for file in sorted(os.listdir(location)):
            child, sort_order = construct_node(os.path.join(location, file), current_path, node_cache, channel,
                                               sort_order=sort_order)
            if child:
                contains = contains.union(child.get("contains", set()))
                contains = contains.union({child["kind"]})

        node["contains"] = list(contains)

    else:
        extension = base_name.split(".")[-1]
        kind = file_kind_map.get(extension)

        if not kind:
            return None, sort_order
        # No metadata library seems to work in Python 3.5, so let's skip this for now.
        # elif kind in ["Video", "Audio", "Image"]:
        #     from hachoir_core.cmd_line import unicodeFilename
        #     from hachoir_parser import createParser
        #     from hachoir_metadata import extractMetadata
        #
        #     filename = unicodeFilename(location)
        #     parser = createParser(filename, location)
        #
        #     if parser:
        #         info = extractMetadata(parser)
        #         data_meta = {}
        #         for meta_key, data_fn in file_meta_data_map.items():
        #             if data_fn(info):
        #                 data_meta[meta_key] = data_fn(info)
        #         if data_meta.get("codec"):
        #             data_meta["{kind}_codec".format(kind=kind.lower())] = data_meta["codec"]
        #             del data_meta["codec"]
        #         data_meta.update(meta_data)
        #         meta_data = data_meta
        elif kind == "Exercise":
            zf = zipfile.ZipFile(open(location, "rb"), "r")
            try:
                data_meta = json.loads(zf.read("exercise.json").decode(encoding='UTF-8'))
            except KeyError:
                data_meta = {}
                logging.debug("No exercise metadata available in zipfile")
            # Assume information in an external metadata file is more up to date than the internal one.
            data_meta.update(meta_data)
            meta_data = data_meta
            try:
                assessment_items = json.loads(zf.read("assessment_items.json").decode(encoding='UTF-8'))
                items = []
                for assessment_item in assessment_items:
                    md5 = hashlib.md5()
                    md5.update(str(assessment_item).encode("UTF-8"))
                    items.append({
                        "id": md5.hexdigest(),
                        "item_data": json.dumps(assessment_item),
                        "author_names": ""
                    })
                assessment_items = items
                node["uses_assessment_items"] = True
            except KeyError:
                logging.debug("No assessment items found in zipfile")
            for filename in zf.namelist():
                if filename and os.path.splitext(filename)[0] != "json":
                    node_cache["AssessmentFiles"].add(extract_and_cache_file(zf, filename=filename))

        id = file_md5(channel, location)

        node.update({
            "id": id,
            "kind": kind,
        })

        if kind != "Exercise":
            node.update({
                "format": extension,
            })
            # Copy over content
            content_dir = os.path.join(os.path.join(os.getcwd(), "build", "content"))
            if not os.path.exists(content_dir):
                os.mkdir(content_dir)
            shutil.copy(location, os.path.join(os.path.join(os.getcwd(), "build", "content"), id + "." + extension))
            logging.debug("%s file %s to local content directory." % ("Copied", slug))

        node.update(meta_data)

    # Verify some required fields:
    if "title" not in node:
        logging.warning("Title missing from file {base_name}, using file name instead".format(base_name=base_name))
        if os.path.isdir(location):
            node["title"] = base_name
        else:
            node["title"] = os.path.splitext(base_name)[0]

    # Clean up some fields:
    # allow tags and keywords to be a single item as a string, convert to list
    for key in ["tags", "keywords"]:
        if isinstance(node.get(key, []), str):
            node[key] = [node[key]]

    nodecopy = copy.deepcopy(node)
    if kind == "Exercise":
        nodecopy["all_assessment_items"] = [{"id": item.get("id")} for item in assessment_items]
        node_cache["AssessmentItem"].extend(assessment_items)
    node_cache["Node"].append(nodecopy)

    return node, sort_order + 1


def annotate_related_content(node_data):
    slug_cache = {item.get("slug"): item for item in node_data}

    for item in node_data:
        # allow related_content to be a single item as a string
        if isinstance(item.get("related_content", []), str):
            item["related_content"] = [item["related_content"]]
        # or a list of several related items
        for i, related_item in enumerate(item.get("related_content", [])):
            content = slug_cache.get(slugify(related_item.split(".")[0].encode("UTF-8")))
            if content:
                item["related_content"][i] = {
                    "id": content.get("id"),
                    "kind": content.get("kind"),
                    "path": content.get("path"),
                    "title": content.get("title"),
                }
            else:
                item["related_content"][i] = None
        if item.get("related_content", []):
            item["related_content"] = [related_item for related_item in item["related_content"] if related_item]
            if not item["related_content"]:
                del item["related_content"]


def retrieve_import_data(path=None, channel=None):
    if not os.path.isdir(path):
        raise Exception("The specified path is not a valid directory")

    node_cache = {
        "Node": [],
        "Slugs": set(),
        "AssessmentItem": [],
        "AssessmentFiles": set(),
    }

    construct_node(path, "", node_cache, channel)

    assessment_items = node_cache["AssessmentItem"]

    assessment_files = node_cache["AssessmentFiles"]

    node_data = node_cache["Node"]

    del node_cache["Slugs"]

    annotate_related_content(node_data)

    return node_data, assessment_items, assessment_files
