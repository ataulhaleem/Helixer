from sequence_helpers import reverse_complement
from dustdas import gffhelper, fastahelper
import argparse
import itertools
import copy
import sys


def gff3_to_json(gff3):
    gh = gffhelper.read_gff_file(infile=gff3)
    transcripts = 0
    for entry in gh:
        if entry.type == 'transcript':
            transcripts += 1
    print(transcripts)


def fasta_to_json(fasta):
    fh = fastahelper.FastaParser()
    meta_genome = MetaInfoGenome()
    meta_genome.maybe_add_info_from_fasta(fasta)
    for infos, seq in fh.read_fasta(fasta):
        mis = MetaInfoSequence()
        mis.add_sequence(fasta_header=infos, sequence=seq)
        meta_genome.add_sequence_meta_info(mis)
        print(mis.to_json())
        #x = reverse_complement(seq)
        #for _ in gen_mers(seq, 2):
        #    pass
        #print(x[:20])
        print(infos)
        print(seq[:20])
    print(meta_genome.__dict__)


class GenericData(object):
    """Handles basic to/from json conversions for self and any sub data it holds"""
    def __init__(self):
        # attribute name, exported_to_json, expected_inner_type, data_structure
        # where data structure is always `None` and type the result of `type(self.attr)` unless `expected_inner_type`
        # is an instance of this class (GenericData), then `data_structure` denotes any grouping class (e.g. list),
        # or is still `None` if not grouped at all
        self.spec = [('spec', False, list, None), ]

    def to_jsonable(self):
        out = {}
        for key in copy.deepcopy(self.__dict__):
            raw = self.__getattribute__(key)
            cleaned, is_exported = self._prep_main(key, raw, towards_json=True)
            if is_exported:
                out[key] = cleaned
        return out

    def load_jsonable(self, jsonable):
        for key in jsonable:
            raw = jsonable[key]
            cleaned, is_exported = self._prep_main(key, raw, towards_json=False)
            assert is_exported, "Expected only exported attributes to be found in the json, error at {}".format(
                key
            )
            self.__setattr__(key, cleaned)

    def _prep_main(self, key, raw, towards_json=True):
        _, is_exported, expected_type, data_structure = self.get_key_spec(key)

        if data_structure is None:
            out = self._prep_none(expected_type, raw, towards_json)
        elif data_structure in (list, tuple):  # maybe could also have set and iter, but idk why you'd need this
            out = self._prep_list_like(expected_type, raw, data_structure, towards_json)
        elif data_structure is dict:
            out = self._prep_dict(expected_type, raw, towards_json)
        else:
            raise ValueError("no export method prepared for data_structure of type: {}".format(data_structure))
        return copy.deepcopy(out), is_exported

    def get_key_spec(self, key):
        key_spec = [s for s in self.spec if s[0] == key]
        assert len(key_spec) == 1, "{} attribute has {} instead of 1 matches in spec".format(key, len(key_spec))
        return key_spec[0]

    @staticmethod
    def _confirm_type(expected_type, to_check):
        assert isinstance(to_check, expected_type), "type: ({}) differs from expectation in spec ({})".format(
            type(to_check), expected_type
        )

    def _prep_none(self, expected_type, raw, towards_json=True):
        if towards_json:
            return self._prep_none_to_json(expected_type, raw)
        else:
            return self._prep_none_from_json(expected_type, raw)

    def _prep_none_to_json(self, expected_type, raw):
        out = raw
        self._confirm_type(expected_type, out)
        if issubclass(expected_type, GenericData):
            out = out.to_jsonable()
        return out

    def _prep_none_from_json(self, expected_type, raw):
        out = raw
        if issubclass(expected_type, GenericData):
            out = expected_type()
            out.load_jsonable(raw)
        self._confirm_type(expected_type, out)
        return out

    def _prep_list_like(self, expected_type, raw, data_structure, towards_json=True):
        out = []
        for item in raw:
            out.append(self._prep_none(expected_type, item, towards_json))
        if not towards_json:
            out = data_structure(out)
        return out

    def _prep_dict(self, expected_type, raw, towards_json=True):
        out = {}
        for key in raw:
            out[key] = self._prep_none(expected_type, raw[key], towards_json)
        return out


class StructuredGenome(GenericData):
    """Handles meta info for genome and included sequences"""
    def __init__(self):
        super().__init__()
        # todo, make GenericData more specific below
        self.spec += [("sequences", True, GenericData, list),
                      ("meta_info", True, GenericData, None)]
        self.meta_info = MetaInfoGenome()
        self.sequences = []

    def add_fasta(self, fasta):
        self.meta_info.maybe_add_info_from_fasta(fasta)
        fh = fastahelper.FastaParser()
        for infos, seq in fh.read_fasta(fasta):
            mis = MetaInfoSequence()
            mis.add_sequence(fasta_header=infos, sequence=seq)
            self.meta_info.add_sequence_meta_info(mis)
            # todo, save sequences and their meta info while going through!
            # todo, was here!


class MetaInfoGenome(GenericData):
    def __init__(self):
        super().__init__()
        self.spec += [('species', True, str, None),
                      ('accession', True, str, None),
                      ('version', True, str, None),
                      ('acquired_from', True, str, None),
                      ('total_bp', True, int, None),
                      ('gc_content', True, int, None),
                      ('cannonical_kmer_content', True, dict, None),
                      ('ambiguous_content', True, int, None)]
        # will need to be set
        self.species = ""
        self.accession = ""
        self.version = ""
        self.acquired_from = ""
        # will be calculated as sequences are added
        self.total_bp = 0
        self.gc_content = 0
        self.cannonical_kmer_content = {}
        self.ambiguous_content = 0

    def maybe_add_info_from_fasta(self, fasta):
        # todo, could possibly parse out version info or accession or whatever??
        if not self.species:
            self.species = self.species_from_path(fasta)

    @staticmethod
    def species_from_path(fasta_path):
        if '/' in fasta_path:
            fasta_path = fasta_path.split('/')[-1]
        if fasta_path.endswith('.fasta'):
            species = fasta_path.replace('.fasta', '')
        elif fasta_path.endswith('.fa'):
            species = fasta_path.replace('.fa', '')
        else:
            species = fasta_path
        return species

    def add_sequence_meta_info(self, seq_met_info):
        self.total_bp += seq_met_info.total_bp
        self.gc_content += seq_met_info.gc_content
        self.cannonical_kmer_content = add_paired_dictionaries(self.cannonical_kmer_content,
                                                               seq_met_info.cannonical_kmer_content)
        self.ambiguous_content += seq_met_info.ambiguous_content


class MetaInfoSequence(GenericData):
    def __init__(self):
        super().__init__()
        self.spec += [("deprecated_header", True, str, None),
                      ("seqid", True, str, None),
                      ("total_bp", True, int, None),
                      ("cannonical_kmer_content", True, dict, None),
                      ("gc_content", True, int, None),
                      ("ambiguous_content", True, int, None)]
        self.deprecated_header = ""
        self.seqid = ""
        self.total_bp = 0
        self.gc_content = 0
        self.cannonical_kmer_content = {}
        self.ambiguous_content = 0

    def add_sequence(self, fasta_header, sequence, id_delim=' ', smallest_mer=2, largest_mer=2):
        self.deprecated_header = fasta_header
        self.seqid = fasta_header.split(id_delim)[0]
        self.total_bp = len(sequence)
        self.calculate_and_set_meta(sequence.lower(), smallest_mer, largest_mer)

    def calculate_and_set_meta(self, sequence, smallest_mer, largest_mer):
        # go through all the bp and count all the things
        gc = 0
        gc_bps = ('g', 'c')
        ambiguous = 0
        known_bps = ('a', 't', 'c', 'g')
        for bp in sequence:
            if bp.lower() in gc_bps:
                gc += 1
            if bp not in known_bps:
                ambiguous += 1
        # count all kmers
        self.cannonical_kmer_content = {}
        for k in range(smallest_mer, largest_mer + 1):
            mer_counter = MerCounter(k)
            for mer in gen_mers(sequence, k):
                mer_counter.add_mer(mer)
            self.cannonical_kmer_content[k] = mer_counter.export()
        # record
        self.gc_content = gc
        self.ambiguous_content = ambiguous

    def to_json(self):
        return self.__dict__


class MerCounter(object):
    amb = 'ambiguous_mers'

    def __init__(self, k):
        self.k = k
        self.counts = {}
        # calculate all possible mers of this length, and set counter to 0
        for mer in itertools.product('atcg', repeat=k):
            mer = ''.join(mer)
            self.counts[mer] = 0
        self.counts[MerCounter.amb] = 0
        # most recent base pairs of up to length k
        self.sliding_mer = []

    def add_mer(self, mer):
        try:
            self.counts[mer] += 1
        except KeyError:
            self.counts[MerCounter.amb] += 1

    def export(self):
        out = copy.deepcopy(self.counts)
        for key in self.counts:
            if key != MerCounter.amb:
                # collapse to cannonical kmers
                rc_key = reverse_complement(key)
                if key != min(key, rc_key):
                    out[rc_key] += out[key]
                    out.pop(key)
        return out


def gen_mers(sequence, k):
    for i in range(len(sequence) - k):
        yield sequence[i:(i+k)]


def add_paired_dictionaries(add_to, add_from):
    add_to = copy.deepcopy(add_to)
    for key in add_from:
        if key not in add_to:
            add_to[key] = copy.deepcopy(add_from[key])
        elif isinstance(add_to[key], dict):
            add_to[key] = add_paired_dictionaries(add_to[key], add_from[key])
        else:
            add_to[key] += add_from[key]
    return add_to


def main(gff3, fasta, fileout):
    #annotation = gff3_to_json(gff3)
    sequences = fasta_to_json(fasta)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--gff3', help='gff3 formatted file to parse / standardize')
    parser.add_argument('--fasta', help='fasta file to parse standardize', required=True)
    parser.add_argument('-o', '--out', help='output prefix, defaults to "standardized"', default="standardized")
    args = parser.parse_args()
    main(args.gff3, args.fasta, args.out)
