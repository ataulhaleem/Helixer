from structure import GenericData
from dustdas import gffhelper
import logging
import copy
import intervaltree


class FeatureDecoder(object):
    def __init__(self):
        self.error_buffer = 2000
        # gene like, generally having a collection of transcripts
        self.gene = 'gene'
        self.super_gene = 'super_gene'
        self.ncRNA_gene = 'ncRNA_gene'
        self.pseudogene = 'pseudogene'
        self.gene_level = [self.gene, self.super_gene, self.ncRNA_gene, self.pseudogene]

        # transcript like, generally having a collection of exons, indicating how they are spliced
        # also ultimately, if not explicitly having a transcription start and termination site
        self.mRNA = 'mRNA'
        self.tRNA = 'tRNA'
        self.rRNA = 'rRNA'
        self.miRNA = 'miRNA'
        self.snoRNA = 'snoRNA'
        self.snRNA = 'snRNA'
        self.SRP_RNA = 'SRP_RNA'
        self.lnc_RNA = 'lnc_RNA'
        self.pre_miRNA = 'pre_miRNA'
        self.RNase_MRP_RNA = 'RNase_MRP_RNA'
        self.transcript = 'transcript'
        self.primary_transcript = 'primary_transcript'
        self.pseudogenic_transcript = 'pseudogenic_transcript'  # which may or may not be transcribed, hard to say
        self.transcribed = [self.mRNA, self.transcript, self.tRNA, self.primary_transcript, self.rRNA, self.miRNA,
                            self.snoRNA, self.snRNA, self.SRP_RNA, self.lnc_RNA, self.pre_miRNA, self.RNase_MRP_RNA,
                            self.pseudogenic_transcript]

        # regions of original (both) or processed (exon) transcripts
        self.exon = 'exon'
        self.intron = 'intron'
        self.sub_transcribed = [self.exon, self.intron]

        # sub-exon-level categorization (but should have transcribed as parent)
        self.cds = 'CDS'
        self.five_prime_UTR = 'five_prime_UTR'
        self.three_prime_UTR = 'three_prime_UTR'
        self.coding_info = [self.cds, self.five_prime_UTR, self.three_prime_UTR]

        # point annotations
        self.TSS = 'TSS'  # transcription start site
        self.TTS = 'TTS'  # transcription termination site
        self.start_codon = 'start_codon'
        self.stop_codon = 'stop_codon'
        self.donor_splice_site = 'donor_splice_site'
        self.acceptor_splice_site = 'acceptor_splice_site'
        # use the following when the far side of a splice site is on a different strand and/or sequence
        # does not imply an intron!
        # e.g. for trans-splicing
        self.trans_donor_splice_site = 'trans_donor_splice_site'
        self.trans_acceptor_splice_site = 'trans_acceptor_splice_site'
        self.point_annotations = [self.TSS, self.TTS, self.start_codon, self.stop_codon, self.donor_splice_site,
                                  self.acceptor_splice_site, self.trans_donor_splice_site,
                                  self.trans_acceptor_splice_site]

        # regions (often but not always included so one knows the size of the chromosomes / contigs / whatever
        self.region = 'region'
        self.chromosome = 'chromosome'
        self.supercontig = 'supercontig'
        self.regions = [self.region, self.chromosome, self.supercontig]

        # things that don't appear to really be annotations
        self.match = 'match'
        self.cDNA_match = 'cDNA_match'
        self.ignorable = [self.match, self.cDNA_match]

        # for mistakes or near-mistakes / marking partials
        self.error = 'error'
        self.status_coding = 'status_coding'
        self.status_intron = 'status_intron'
        self.status_five_prime_UTR = 'status_five_prime_UTR'
        self.status_three_prime_UTR = 'status_three_prime_UTR'
        self.status_intergenic = 'status_intergenic'
        self.statuses = [self.status_coding, self.status_intron, self.status_five_prime_UTR,
                         self.status_three_prime_UTR, self.status_intergenic]
        # and putting them together
        self.on_sequence = self.sub_transcribed + self.coding_info + self.point_annotations
        self.known = self.gene_level + self.transcribed + self.sub_transcribed + self.coding_info + \
                     self.point_annotations + self.regions + self.ignorable + [self.error] + self.statuses


class IDMaker(object):
    def __init__(self, prefix='', width=6):
        self._counter = 0
        self.prefix = prefix
        self._seen = set()
        self._width = width

    @property
    def seen(self):
        return self._seen

    def next_unique_id(self, suggestion=None):
        if suggestion is not None:
            suggestion = str(suggestion)
            if suggestion not in self._seen:
                self._seen.add(suggestion)
                return suggestion
        # you should only get here if a) there was no suggestion or b) it was not unique
        return self._new_id()

    def _new_id(self):
        new_id = self._fmt_id()
        self._seen.add(new_id)
        self._counter += 1
        return new_id

    def _fmt_id(self):
        to_format = '{}{:0' + str(self._width) + '}'
        return to_format.format(self.prefix, self._counter)


class AnnotatedGenome(GenericData):
    def __init__(self):
        super().__init__()
        self.spec += [('super_loci', True, SuperLoci, list),
                      ('meta_info', True, MetaInfoAnnoGenome, None),
                      ('meta_info_sequences', True, MetaInfoAnnoSequence, dict),
                      ('gffkey', False, FeatureDecoder, None),
                      ('transcript_ider', False, IDMaker, None),
                      ('feature_ider', False, IDMaker, None)]

        self.super_loci = []
        self.meta_info = MetaInfoAnnoGenome()
        self.meta_info_sequences = {}
        self.gffkey = FeatureDecoder()
        self.transcript_ider = IDMaker(prefix='trx')
        self.feature_ider = IDMaker(prefix='ftr')

    def add_gff(self, gff_file, genome):
        for seq in genome.sequences:
            mi = MetaInfoAnnoSequence()
            mi.seqid = seq.meta_info.seqid
            mi.total_bp = seq.meta_info.total_bp
            self.meta_info_sequences[mi.seqid] = mi
        for entry_group in self.group_gff_by_gene(gff_file):
            new_sl = SuperLoci(self)
            new_sl.add_gff_entry_group(entry_group)
            self.super_loci.append(new_sl)
            if not new_sl.transcripts and not new_sl.features:
                print('{} from {} with {} transcripts and {} features'.format(new_sl.id,
                                                                              entry_group[0].source,
                                                                              len(new_sl.transcripts),
                                                                              len(new_sl.features)))

    def useful_gff_entries(self, gff_file):
        skipable = self.gffkey.regions + self.gffkey.ignorable
        reader = gffhelper.read_gff_file(gff_file)
        for entry in reader:
            if entry.type not in self.gffkey.known:
                raise ValueError("unrecognized feature type from gff: {}".format(entry.type))
            if entry.type not in skipable:
                yield entry

    def group_gff_by_gene(self, gff_file):
        reader = self.useful_gff_entries(gff_file)
        gene_group = [next(reader)]
        for entry in reader:
            if entry.type == 'gene':
                yield gene_group
                gene_group = [entry]
            else:
                gene_group.append(entry)
        yield gene_group


class MetaInfoAnnotation(GenericData):
    def __init__(self):
        super().__init__()
        self.spec += [('number_genes', True, int, None),
                      ('bp_intergenic', True, int, None),
                      ('bp_coding', True, int, None),
                      ('bp_intronic', True, int, None),
                      ('bp_3pUTR', True, int, None),
                      ('bp_5pUTR', True, int, None)]

        # todo, does this make sense, considering that any given bp could belong to multiple of the following
        self.number_genes = 0
        self.bp_intergenic = 0
        self.bp_coding = 0
        self.bp_intronic = 0
        self.bp_3pUTR = 0
        self.bp_5pUTR = 0


class MetaInfoAnnoGenome(MetaInfoAnnotation):
    def __init__(self):
        super().__init__()
        self.spec += [('species', True, str, None),
                      ('accession', True, str, None),
                      ('version', True, str, None),
                      ('acquired_from', True, str, None)]

        self.species = ""
        self.accession = ""
        self.version = ""
        self.acquired_from = ""


class MetaInfoAnnoSequence(MetaInfoAnnotation):
    def __init__(self):
        super().__init__()
        self.spec += [('seqid', True, str, None),
                      ('total_bp', True, int, None)]
        self.seqid = ""
        self.total_bp = 0


class FeatureLike(GenericData):
    def __init__(self):
        super().__init__()
        self.spec += [('id', True, str, None),
                      ('type', True, str, None),
                      ('is_partial', True, bool, None),
                      ('is_reconstructed', True, bool, None),
                      ('is_type_in_question', True, bool, None)]
        self.id = ''
        self.type = ''
        self.is_partial = False
        self.is_reconstructed = False
        self.is_type_in_question = False


class SuperLoci(FeatureLike):
    # normally a loci, some times a short list of loci for "trans splicing"
    # this will define a group of exons that can possibly be made into transcripts
    # AKA this if you have to go searching through a graph for parents/children, at least said graph will have
    # a max size defined at SuperLoci
    def __init__(self, genome):
        super().__init__()
        self.spec += [('transcripts', True, Transcribed, dict),
                      ('features', True, StructuredFeature, dict),
                      ('ids', True, list, None),
                      ('genome', False, AnnotatedGenome, None),
                      ('_dummy_transcript', False, Transcribed, None)]
        self.transcripts = {}
        self.features = {}
        self.ids = []
        self._dummy_transcript = None
        self.genome = genome

    def dummy_transcript(self):
        if self._dummy_transcript is not None:
            return self._dummy_transcript
        else:
            # setup new blank transcript
            transcript = Transcribed()
            transcript.id = self.genome.transcript_ider.next_unique_id()  # add an id
            self._dummy_transcript = transcript  # save to be returned by next call of dummy_transcript
            self.transcripts[transcript.id] = transcript  # save into main dict of transcripts
            return transcript

    def add_gff_entry(self, entry):
        gffkey = self.genome.gffkey
        if entry.type == gffkey.gene:
            self.type = gffkey.gene
            gene_id = entry.get_ID()
            self.id = gene_id
            self.ids.append(gene_id)
        elif entry.type in gffkey.transcribed:
            parent = self.one_parent(entry)
            assert parent == self.id, "not True :( [{} == {}]".format(parent, self.id)
            transcript = Transcribed()
            transcript.add_data(self, entry)
            self.transcripts[transcript.id] = transcript
        elif entry.type in gffkey.on_sequence:
            feature = StructuredFeature()
            feature.add_data(self, entry)
            self.features[feature.id] = feature

    def add_gff_entry_group(self, entries):
        entries = list(entries)
        for entry in entries:
            self.add_gff_entry(entry)
        self.check_and_fix_structure(entries)

    @staticmethod
    def one_parent(entry):
        parents = entry.get_Parent()
        assert len(parents) == 1
        return parents[0]

    def get_matching_transcript(self, entry):
        # deprecating
        parent = self.one_parent(entry)
        try:
            transcript = self.transcripts[-1]
            assert parent == transcript.id
        except IndexError:
            raise NoTranscriptError("0 transcripts found")
        except AssertionError:
            transcripts = [x for x in self.transcripts if x.id == parent]
            if len(transcripts) == 1:
                transcript = transcripts[0]
            else:
                raise NoTranscriptError("can't find {} in {}".format(parent, [x.id for x in self.transcripts]))
        return transcript

    def _mark_erroneous(self, entry):
        assert entry.type in self.genome.gffkey.gene_level
        feature = StructuredFeature()
        feature.start = entry.start
        feature.end = entry.end
        feature.type = self.genome.gffkey.error
        feature.id = self.genome.feature_ider.next_unique_id()
        logging.warning(
            '{species}:{seqid}, {start}-{end}:{gene_id} by {src}, No valid features found - marking erroneous'.format(
                src=entry.source, species=self.genome.meta_info.species, seqid=entry.seqid, start=entry.start,
                end=entry.end, gene_id=self.id
            ))
        self.features[feature.id] = feature

    def check_and_fix_structure(self, entries):
        # if it's empty (no bottom level features at all) mark as erroneous
        if not self.features:
            self._mark_erroneous(entries[0])

        # collapse identical final features
        self.collapse_identical_features()
        # check that all non-exons are in regions covered by an exon
        self.maybe_reconstruct_exons()
        # recreate transcribed / exon as necessary, but with reconstructed flag (also check for and mark pseudogenes)
        pass  # todo

    def collapse_identical_features(self):
        i = 0
        features = self.features
        while i < len(features) - 1:
            # sort and copy keys so that removal of the merged from the dict causes neither sorting nor looping trouble
            feature_keys = sorted(features.keys())
            feature = features[feature_keys[i]]
            for j in range(i + 1, len(feature_keys)):
                o_key = feature_keys[j]
                if feature.fully_overlaps(features[o_key]):
                    feature.merge(features[o_key])  # todo logging debug
                    features.pop(o_key)
                    logging.debug('removing {} from {} as it overlaps {}'.format(o_key, self.id, feature.id))
            i += 1

    def maybe_reconstruct_exons(self):
        """creates any exons necessary, so that all CDS/UTR is contained within an exon"""
        # because introns will be determined from exons, every CDS etc, has to have an exon
        new_exons = []
        exons = self.exons()
        coding_info = self.coding_info_features()
        for f in coding_info:
            if not any([f.is_contained_in(exon) for exon in exons]):
                new_exons.append(f.reconstruct_exon())  # todo, logging info/debug?
        for e in new_exons:
            self.features[e.id] = e

    def exons(self):
        return [self.features[x] for x in self.features if self.features[x].type == self.genome.gffkey.exon]

    def coding_info_features(self):
        return [self.features[x] for x in self.features if self.features[x].type in self.genome.gffkey.coding_info]

    def implicit_to_explicit(self):
        # make introns, tss, tts, and maybe start/stop codons, utr if necessary
        # add UTR if they are not there
        # check start stop codons and splice sites against sequence and flag errors
        pass

    def check_sequence_assumptions(self):
        pass

    def add_to_interval_tree(self, itree):
        pass  # todo, make sure at least all features are loaded to interval tree

    def load_jsonable(self, jsonable):
        super().load_jsonable(jsonable)
        # todo restore super_loci objects, transcript objects, feature_objects to self and children


class NoTranscriptError(Exception):
    pass


class Transcribed(FeatureLike):
    def __init__(self):
        super().__init__()
        self.spec += [('super_loci', False, SuperLoci, None),
                      ('features', True, list, None)]

        self.super_loci = None
        self.features = []

    def add_data(self, super_loci, gff_entry):
        self.super_loci = super_loci
        self.id = gff_entry.get_ID()
        self.type = gff_entry.type

    def link_to_feature(self, feature_id):
        self.features.append(feature_id)

    def remove_feature(self, feature_id):
        self.features.pop(self.features.index(feature_id))



class StructuredFeature(FeatureLike):
    def __init__(self):
        super().__init__()
        self.spec += [('start', True, int, None),
                      ('end', True, int, None),
                      ('seqid', True, str, None),
                      ('strand', True, str, None),
                      ('score', True, float, None),
                      ('source', True, str, None),
                      ('frame', True, str, None),
                      ('transcripts', False, list, None),
                      ('super_loci', False, SuperLoci, None)]

        self.start = -1
        self.end = -1
        self.seqid = ''
        self.strand = '.'
        self.frame = '.'
        self.score = -1.
        self.source = ''
        self.transcripts = []
        self.super_loci = None

    @property
    def py_start(self):
        return self.start - 1

    @property
    def py_end(self):
        return self.end

    def add_data(self, super_loci, gff_entry):
        gffkey = super_loci.genome.gffkey
        fid = gff_entry.get_ID()
        self.id = super_loci.genome.feature_ider.next_unique_id(fid)
        self.type = gff_entry.type
        self.start = gff_entry.start
        self.end = gff_entry.end
        self.strand = gff_entry.strand
        self.seqid = gff_entry.seqid
        try:
            self.score = float(gff_entry.score)
        except ValueError:
            pass
        self.super_loci = super_loci
        new_transcripts = gff_entry.get_Parent()
        if not new_transcripts:
            self.type = gffkey.error
            logging.warning('{species}:{seqid}:{fid}:{new_id} - No Parents listed'.format(
                species=super_loci.genome.meta_info.species, seqid=self.seqid, fid=fid, new_id=self.id
            ))
        for transcript_id in new_transcripts:
            new_t_id = transcript_id
            try:
                transcript = super_loci.transcripts[transcript_id]
                transcript.link_to_feature(self.id)
            except KeyError:
                if transcript_id == super_loci.id:
                    # if we just skipped the transcript, and linked to gene, use dummy transcript in between
                    transcript = super_loci.dummy_transcript()
                    logging.info(
                        '{species}:{seqid}:{fid}:{new_id} - Parent gene instead of transcript, recreating'.format(
                            species=super_loci.genome.meta_info.species, seqid=self.seqid, fid=fid, new_id=self.id
                        ))
                    transcript.link_to_feature(self.id)
                    new_t_id = transcript.id
                else:
                    self.type = gffkey.error
                    new_t_id = None
                    logging.warning(
                        '{species}:{seqid}:{fid}:{new_id} - Parent: "{parent}" not found at loci'.format(
                            species=super_loci.genome.meta_info.species, seqid=self.seqid, fid=fid, new_id=self.id,
                            parent=transcript_id
                        ))
            self.link_to_transcript_and_back(new_t_id)

    def link_to_transcript_and_back(self, transcript_id):
        transcript = self.super_loci.transcripts[transcript_id]  # get transcript
        transcript.link_to_feature(self.id)  # link to and from self
        self.transcripts.append(transcript_id)

    def fully_overlaps(self, other):
        should_match = ['type', 'start', 'end', 'seqid', 'strand', 'frame']
        does_it_match = [self.__getattribute__(x) == other.__getattribute__(x) for x in should_match]
        same_gene = self.super_loci is other.super_loci
        out = False
        if all(does_it_match + [same_gene]):
            out = True
        return out

    def is_contained_in(self, other):
        should_match = ['seqid', 'strand', 'frame']
        does_it_match = [self.__getattribute__(x) == other.__getattribute__(x) for x in should_match]
        same_gene = self.super_loci is other.super_loci
        coordinates_within = self.start >= other.start and self.end <= other.end
        return all(does_it_match + [coordinates_within, same_gene])

    def reconstruct_exon(self):
        """creates an exon exactly containing this feature"""
        exon = self.clone()
        exon.type = self.super_loci.genome.gffkey.exon
        return exon

    def clone(self, copy_transcripts=True):
        """makes valid, independent clone/copy of this feature"""
        new = StructuredFeature()
        copy_over = copy.deepcopy(list(new.__dict__.keys()))

        for to_skip in ['super_loci', 'id', 'transcripts']:
            copy_over.pop(copy_over.index(to_skip))

        # handle can't just be copied things
        new.super_loci = self.super_loci
        new.id = self.super_loci.genome.feature_ider.next_unique_id()
        if copy_transcripts:
            for transcript in self.transcripts:
                new.link_to_transcript_and_back(transcript)

        # copy the rest
        for item in copy_over:
            new.__setattr__(item, copy.deepcopy(self.__getattribute__(item)))
        return new

    def merge(self, other):
        assert self is not other
        # move transcript reference from other to self
        for transcript_id in copy.deepcopy(other.transcripts):
            self.link_to_transcript_and_back(transcript_id)
            other.de_link_from_transcript(transcript_id)

    def de_link_from_transcript(self, transcript_id):
        transcript = self.super_loci.transcripts[transcript_id]  # get transcript
        transcript.remove_feature(self.id)  # drop other
        self.transcripts.pop(self.transcripts.index(transcript_id))

    def is_plus_strand(self):
        if self.strand == '+':
            return True
        elif self.strand == '-':
            return False
        else:
            raise ValueError('strand should be +- {}'.format(self.strand))

    def upstream(self):
        if self.is_plus_strand():
            return self.start
        else:
            return self.end

    def downstream(self):
        if self.is_plus_strand():
            return self.end
        else:
            return self.start

    # inclusive and from 1 coordinates
    def upstream_from_interval(self, interval):
        if self.is_plus_strand():
            return interval.begin + 1
        else:
            return interval.end

    def downstream_from_interval(self, interval):
        if self.is_plus_strand():
            return interval.end
        else:
            return interval.begin + 1


#### section TranscriptInterpreter, might end up in a separate file later
class TranscriptStatus(object):
    """can hold all the info on current status of a transcript"""
    def __init__(self):
        # initializes to 5' UTR
        self.genic = True
        self.in_intron = False
        self.seen_start = False
        self.seen_stop = False


class TranscriptInterpreter(object):
    """takes raw/from-gff transcript, and makes totally explicit"""
    def __init__(self, transcript):
        self.status = TranscriptStatus()
        self.super_loci = transcript.super_loci
        self.gffkey = transcript.super_loci.genome.gffkey
        self.transcript = transcript
        self.features = []  # will hold all the 'fixed' features

    def get_status(self, last_seen, pre_intron):
        # status has been explicitly set already (e.g. at sequence start, after error)
        if last_seen in self.gffkey.statuses:
            current = last_seen
        # for change of transcribed/coding status, update current and pre_intron status
        elif last_seen == self.gffkey.TSS:
            current = self.gffkey.status_five_prime_UTR
            pre_intron = current
        elif last_seen == self.gffkey.start_codon:
            current = self.gffkey.status_coding
            pre_intron = current
        elif last_seen == self.gffkey.stop_codon:
            current = self.gffkey.status_three_prime_UTR
            pre_intron = current
        elif last_seen == self.gffkey.TTS:
            current = self.gffkey.status_intergenic
            pre_intron = current
        # change splice status, update only current
        elif last_seen == self.gffkey.donor_splice_site:
            current = self.gffkey.status_intron
        elif last_seen == self.gffkey.acceptor_splice_site:
            current = pre_intron
        else:
            raise ValueError('do not know how to set status after feature of type {}'.format(last_seen))
        return current, pre_intron

    def interpret_transition(self, last_feature, pre_intron_status, ivals_before, ivals_after, plus_strand=True):
        status_in = self.get_status(last_feature.type, pre_intron_status)
        sign = 1
        if not plus_strand:
            sign = -1
        before_types = self.possible_types(ivals_before)
        after_types = self.possible_types(ivals_after)
        new_features = []
        # 5' UTR can hit either start codon or splice site
        # todo, WAS HERE, start testing this!
        if status_in == self.gffkey.five_prime_UTR:
            # start codon
            if self.gffkey.five_prime_UTR in before_types and self.gffkey.cds in after_types:
                cds_template = ivals_after[0].data
                assert ivals_before[0].data.end == cds_template.begin  # make sure there is no gap
                assert cds_template.frame == 1  # it better be std frame if it's a start codon
                feature0 = cds_template.clone()
                feature0.start = feature0.end = feature0.upstream()  # start codon is first bp of CDS started
                feature0.type = self.gffkey.start_codon
                new_features.append(feature0)
            # intron
            elif self.gffkey.five_prime_UTR in before_types and self.gffkey.five_prime_UTR in after_types:
                donor_template = ivals_before[0].data
                acceptor_template = ivals_after[0].data
                # make sure there is a gap
                assert donor_template.downstream() * sign < acceptor_template.upstream() * sign
                donor = donor_template.clone()
                # todo, check position of DSS/ASS to be consistent with Augustus, hopefully
                donor.start = donor.end = donor.downstream() + (1 * sign)
                acceptor = acceptor_template.clone()
                acceptor.start = acceptor.end = acceptor.upstream() - (1 * sign)
                new_features += [donor, acceptor]
            else:
                raise ValueError('wrong feature types after five prime: b: {}, a: {}'.format(
                    [x.data.type for x in ivals_before], [x.data.type for x in ivals_after]))
        # todo, transitioning from each status
        # coding
        # intron
        # three prime
        # intergenic?
        # return intervals, pre_intron_status, (and current status?)
        return new_features,

    def interpret_first_pos(self, intervals, plus_strand=True):
        i0 = intervals[0]
        at = i0.data.upstream_from_interval(i0)
        print('at', at)
        new_features = []
        possible_types = self.possible_types(intervals)
        if self.gffkey.five_prime_UTR in possible_types:
            # this should indicate we're good to go and have a transcription start site
            feature0 = i0.data.clone()
            feature0.type = self.gffkey.TSS
            new_features.append(feature0)
            pre_intron_status = self.gffkey.five_prime_UTR
        elif self.gffkey.cds in possible_types:
            # this could be first exon detected or start codon, ultimately, indeterminate
            cds_feature = [x for x in intervals if x.data.type == self.gffkey.cds][0]
            feature0 = cds_feature.clone()  # take CDS, so that 'frame' is maintained
            feature0.type = self.gffkey.status_coding
            new_features.append(feature0)
            pre_intron_status = self.gffkey.status_coding
            # mask a dummy region up-stream as it's very unclear whether it should be intergenic/intronic/utr
            if plus_strand:
                # unless we're at the start of the sequence
                if at != 1:
                    feature_e = cds_feature.clone()
                    feature_e.type = self.gffkey.error
                    feature_e.start = max(1, at - self.gffkey.error_buffer)
                    feature_e.end = at - 1
                    feature_e.frame = '.'
                    new_features.insert(0, feature_e)
            else:
                end_of_sequence = self.get_seq_length(cds_feature.seqid)
                if at != end_of_sequence:
                    feature_e = cds_feature.clone()
                    feature_e.type = self.gffkey.error
                    feature_e.end = min(end_of_sequence, at + self.gffkey.error_buffer)
                    feature_e.start = at + 1
                    feature_e.frame = '.'
                    new_features.insert(0, feature_e)
        else:
            raise ValueError("why's this gene not start with 5' utr nor cds? types: {}, interpretations: {}".format(
                [x.data.type for x in intervals], possible_types))

        feature0.start = feature0.end = at
        # need to return both the features, with [-1] producing last_seen,
        # and the pre_intron status, basically (coding/not)
        return new_features, pre_intron_status

    def intervals_5to3(self, plus_strand=False):
        interval_sets = list(self.organize_and_split_features())
        if not plus_strand:
            interval_sets.reverse()
        return interval_sets

    def decode_raw_features(self, plus_strand=True):
        interval_sets = self.intervals_5to3(plus_strand)
        new_features, pre_intron_status = self.interpret_first_pos(interval_sets[0], plus_strand)
        for i in range(len(interval_sets) - 1):
            status_in, pre_intron_status = self.get_status(new_features[-1].type, pre_intron_status)
            ivals_before = interval_sets[i]
            ivals_after = interval_sets[i + 1]

            print(ivals_before)
            print([(x.data.id, x.data.type) for x in ivals_before])

    def possible_types(self, intervals):
        # shortcuts
        cds = self.gffkey.cds
        five_prime = self.gffkey.five_prime_UTR
        exon = self.gffkey.exon
        three_prime = self.gffkey.three_prime_UTR

        # what we see
        observed_types = [x.data.type for x in intervals]
        set_o_types = set(observed_types)
        # check length
        if len(intervals) not in [1, 2]:
            raise ValueError('check interpretation by hand for transcript start with {}, {}'.format(
                intervals, observed_types
            ))
        # interpret type combination
        if set_o_types == {exon, five_prime} or set_o_types == {five_prime}:
            out = [five_prime]
        elif set_o_types == {exon, three_prime} or set_o_types == {three_prime}:
            out = [three_prime]
        elif set_o_types == {exon}:
            out = [five_prime, three_prime]
        elif set_o_types == {cds, exon} or set_o_types == {cds}:
            out = [cds]
        else:
            raise ValueError('check interpretation of combination for transcript start with {}, {}'.format(
                intervals, observed_types
            ))
        return out

    def organize_and_split_features(self):
        # todo, handle non-single seqid loci
        tree = intervaltree.IntervalTree()
        features = [self.super_loci.features[f] for f in self.features]
        for f in features:
            tree[f.py_start:f.py_end] = f
        tree.split_overlaps()
        # todo, minus strand
        intervals = iter(sorted(tree))
        out = [next(intervals)]
        for interval in intervals:
            if out[-1].begin == interval.begin:
                out.append(interval)
            else:
                yield out
                out = [interval]
        yield out

    def get_seq_length(self, seqid):
        return self.super_loci.genome.meta_info_sequences[seqid].total_bp
