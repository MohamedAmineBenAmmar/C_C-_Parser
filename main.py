import json
import sys
import re
from pycparser import parse_file, c_ast
from pandas import DataFrame

# This is not required if you've installed pycparser into
# your site-packages/ with setup.py
#
sys.path.extend([".", ".."])


RE_CHILD_ARRAY = re.compile(r"(.*)\[(.*)\]")
RE_INTERNAL_ATTR = re.compile("__.*__")


class CJsonError(Exception):
    pass


def memodict(fn):
    """Fast memoization decorator for a function taking a single argument"""

    class memodict(dict):
        def __missing__(self, key):
            ret = self[key] = fn(key)
            return ret

    return memodict().__getitem__


@memodict
def child_attrs_of(klass):
    """
    Given a Node class, get a set of child attrs.
    Memoized to avoid highly repetitive string manipulation

    """
    non_child_attrs = set(klass.attr_names)
    all_attrs = set([i for i in klass.__slots__ if not RE_INTERNAL_ATTR.match(i)])
    return all_attrs - non_child_attrs


def to_dict(node):
    """Recursively convert an ast into dict representation."""
    klass = node.__class__

    result = {}

    # Metadata
    result["_nodetype"] = klass.__name__

    # Local node attributes
    for attr in klass.attr_names:
        result[attr] = getattr(node, attr)

    # Coord object
    if node.coord:
        result["coord"] = str(node.coord)
    else:
        result["coord"] = None

    # Child attributes
    for child_name, child in node.children():
        # Child strings are either simple (e.g. 'value') or arrays (e.g. 'block_items[1]')
        match = RE_CHILD_ARRAY.match(child_name)
        if match:
            array_name, array_index = match.groups()
            array_index = int(array_index)
            # arrays come in order, so we verify and append.
            result[array_name] = result.get(array_name, [])
            if array_index != len(result[array_name]):
                raise CJsonError(
                    "Internal ast error. Array {} out of order. "
                    "Expected index {}, got {}".format(
                        array_name, len(result[array_name]), array_index
                    )
                )
            result[array_name].append(to_dict(child))
        else:
            result[child_name] = to_dict(child)

    # Any child attributes that were missing need "None" values in the json.
    for child_attr in child_attrs_of(klass):
        if child_attr not in result:
            result[child_attr] = None

    return result


def file_to_dict(filename, use_cpp=False):
    """Load C file into dict representation of ast"""
    ast = parse_file(filename, use_cpp=use_cpp)
    return to_dict(ast)


def to_df(elastic_data) -> DataFrame:
    # Create a DataFrame from the dictionary
    df = DataFrame(elastic_data)
    return df


def get_data_elastic_data(ast_dict):
    extracted_data = []
    k = 0

    for section in ast_dict["ext"]:
        base_info = {
            "file": section["coord"],
            "type": section["_nodetype"],
            "name": section["decl"]["name"],
        }
        
        previous_instruction = None
        current_instruction = None
        next_instruction = None
        
        if "body" in section and section['body']['block_items'] != None:
            for instruction in section['body']['block_items']:
                previous_instruction = current_instruction
                # args = None
                # if 'args' in instruction:
                #     args = instruction['args']
                current_instruction = {
                    "type": instruction["_nodetype"],
                    "location": instruction["coord"],
                    # "args": args,
                }
                if k > 0:
                    next_instruction = current_instruction
                    extracted_data[k -1]['next'] = next_instruction
                    
                extracted_data.append({**base_info, 'instruction': current_instruction, 'previous': previous_instruction, 'next': None})
                k += 1
            
    return extracted_data


# ------------------------------------------------------------------------------
if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Some test code...
        # Do trip from C -> ast -> dict -> ast -> json, then print.
        ast_dict = file_to_dict(sys.argv[1])
        elastic_data_dict = get_data_elastic_data(ast_dict)
        
        df = to_df(elastic_data_dict)

        print("c code as dict")
        print(ast_dict)

        print("JSON of code C")
        print(json.dumps(ast_dict, indent=4))

        print("elastic data")
        print(elastic_data_dict)
        
        print("Elastic data as DataFrame")
        print(df)
    else:
        print("Please provide a filename as argument")
