import nltk
import pickle
import string
from gensim.models.keyedvectors import KeyedVectors
import config
import numpy as np
import pandas as pd
import time
import re
from nltk.corpus import wordnet

# nltk.download()
# print ("Downloading stopwords ......")
# nltk.download('stopwords')

# Stopword list
stop_words = nltk.corpus.stopwords.words('english')

# Load Model
print("Loading Pre-Trained Model ..... ")
start = time.perf_counter()
model = KeyedVectors.load_word2vec_format(config.model_path, binary=False)
print("Loaded Pre-Trained Model, time taken", ((time.perf_counter() - start) / 60))

# Config values
threshold = config.threshold
embedding_dim = config.embedding_dim
lmtzr = nltk.WordNetLemmatizer().lemmatize

def clean_text(lines, remove_stopwords=True):
    ''' clean a list of lines'''

    cleaned = list()
    # prepare a translation table to remove punctuation
    table = str.maketrans(' ', ' ', string.punctuation)

    for line in lines:
        # strip source cnn office if it exists
        index = line.find('(CNN)  -- ')
        if index > -1:
            line = line[index + len('(CNN)'):]
        else:
            index = line.find('(CNN)')
            if index > -1:
                line = line[index + len('(CNN)'):]

        # tokenize on white space
        line = line.split()

        # convert to lower case
        line = [word.lower() for word in line]

        # Optionally, remove stop words
        if remove_stopwords:
            line = [w for w in line if w not in stop_words]

        # remove punctuation from each token
        line = [w.translate(table) for w in line]

        # remove tokens with numbers in them
        line = [word for word in line if word.isalpha()]

        # Format words and remove unwanted characters
        text = " ".join(line)
        text = re.sub(r'https?:\/\/.*[\r\n]*', '', text, flags=re.MULTILINE)
        text = re.sub(r'\<a href', ' ', text)
        text = re.sub(r'&amp;', '', text)
        text = re.sub(r'[_"\-;%()|+&=*%.,!?:#$@\[\]/]', ' ', text)
        text = re.sub(r'<br />', ' ', text)
        text = re.sub(r'\'', ' ', text)

        # remove empty strings
        if len(text )> 0 :
            cleaned.append(text)

    return cleaned


def count_words(count_dict, text):
    ''' Count the number of occurrences of each word in a set of text'''
    for sentence in text:
        for word in sentence.split():
            if word not in count_dict:
                count_dict[word] = 1
            else:
                count_dict[word] += 1


def vectorization(text, embeddings_index):
    for sentence in text:
        try:
            for vocab_word in sentence.split():
                embeddings_index[vocab_word] = model[vocab_word]
                #print ("Found Words ", vocab_word)
                # print("Work : {vocab_word} , vector value : {vector_value}".format(vocab_word=vocab_word, vector_value =vector_value))
        except KeyError:
            '''ignore'''
            # print("{vocab_word} not in vocabulary".format(vocab_word=vocab_word))


def missing_word_ratio(word_counts, embeddings_index):
    ''' Find the number of words that are missing from CN, and are used more than our threshold.'''
    missing_words_count = 0
    missing_words = list()

    for word, count in word_counts.items():
        if word not in embeddings_index and word not in missing_words and count > threshold:
            missing_words_count += 1
            missing_words.append(word)
            # print("{word} is missing ".format(word=word))

    missing_ratio = round(missing_words_count / len(word_counts), 4) * 100
    return missing_ratio, missing_words_count


def covert_vocab_to_int(word_counts, embeddings_index):
    # dictionary to convert words to integers
    vocab_to_int = {}

    value = 0
    for word, count in word_counts.items():
        if count > threshold or word in embeddings_index:
            vocab_to_int[word] = value
            value += 1

    # Special tokens that will be added to our vocab
    codes = ["<UNK>", "<PAD>", "<EOS>", "<GO>"]

    # Add codes to vocab
    for code in codes:
        vocab_to_int[code] = len(vocab_to_int)

    # Dictionary to convert integers to words
    int_to_vocab = {}
    for word, value in vocab_to_int.items():
        int_to_vocab[value] = word

    usage_ratio = round(len(vocab_to_int) / len(word_counts), 4) * 100

    print("Total number of unique words:", len(word_counts))
    print("Number of words we will use:", len(vocab_to_int))
    print("Percent of words we will use: {}%".format(usage_ratio))

    return vocab_to_int


def create_combine_word_matrix(vocab_to_int, embeddings_index):
    ''' Need to use 300 for embedding dimensions to match corpus(input data) vectors.
    This will return cobine matriz that would have 'embeddings_index' for from pre-trained word embedding plus
    random embedding generated for words missing in pre-trained word embedding.'''

    nb_words = len(vocab_to_int)

    # Create matrix with default values of zero
    word_embedding_matrix = np.zeros((nb_words, embedding_dim), dtype=np.float32)
    for word, i in vocab_to_int.items():
        if word in embeddings_index:
            word_embedding_matrix[i] = embeddings_index[word]
        else:
            # If word not in CN, create a random embedding for it
            new_embedding = np.array(np.random.uniform(-1.0, 1.0, embedding_dim))
            embeddings_index[word] = new_embedding
            word_embedding_matrix[i] = new_embedding

    # Check if value matches len(vocab_to_int)
    print("word_embedding_matrix length : ", len(word_embedding_matrix))
    return word_embedding_matrix


def convert_to_ints(text, vocab_to_int, eos=False):
    '''Convert words in text to an integer.
       If word is not in vocab_to_int, use UNK's integer.
       Total the number of words and UNKs.
       Add EOS token to the end of texts'''
    ints = []
    word_count = 0
    unk_count = 0
    for sentence in text:
        sentence_ints = []
        for word in sentence.split():
            word_count += 1
            if word in vocab_to_int:
                sentence_ints.append(vocab_to_int[word])
            else:
                sentence_ints.append(vocab_to_int["<UNK>"])
                # print("UNK Word : ", word)
                unk_count += 1
        if eos:
            sentence_ints.append(vocab_to_int["<EOS>"])
        ints.append(sentence_ints)

    unk_percent = round(unk_count / word_count, 4) * 100

    print("Total number of words : ", word_count)
    print("Total number of UNKs : ", unk_count)
    print("Percent of words that are UNK: {}%".format(unk_percent))

    return ints, word_count, unk_count


def create_dataFrame(text):
    '''Create a data frame of the sentence lengths from a text'''
    lengths = []
    for sentence in text:
        lengths.append(len(sentence))
    return pd.DataFrame(lengths, columns=['counts'])


def unk_counter(sentence, vocab_to_int):
    '''Counts the number of time UNK appears in a sentence.'''
    unk_count = 0
    for word in sentence:
        if word == vocab_to_int["<UNK>"]:
            unk_count += 1
    return unk_count


def sort_corplus_old(lengths_articles, int_rep_articles, int_rep_headlines, vocab_to_int):
    ''' Sort the summaries and texts by the length of the texts, shortest to longest
     Limit the length of summaries and texts based on the min and max ranges.
     Remove reviews that include too many UNKs'''

    sorted_articles = []
    sorted_headlines = []
    max_text_length = config.max_text_length
    max_summary_length = config.max_summary_length
    min_length = config.min_length
    unk_text_limit = config.unk_text_limit
    unk_summary_limit = 0

    for length in range(min(lengths_articles.counts), max_text_length):
        # print("length ===", length)
        for count, words in enumerate(int_rep_headlines):
            if (len(int_rep_articles[count]) >= min_length and
                    unk_counter(int_rep_headlines[count], vocab_to_int) <= unk_summary_limit
                    and unk_counter(int_rep_articles[count]) <= unk_text_limit
                    and length == len(int_rep_articles[count], vocab_to_int)):
                sorted_headlines.append(int_rep_headlines[count])
                sorted_articles.append(int_rep_articles[count])

    # Compare lengths to ensure they match
    print(len(sorted_headlines))
    print(len(sorted_articles))

    return sorted_articles, sorted_headlines


def sort_corplus(lengths_articles, int_rep_articles, int_rep_headlines, vocab_to_int):
    ''' Sort the summaries and texts by the length of the texts, shortest to longest
     Limit the length of summaries and texts based on the min and max ranges.
     Remove reviews that include too many UNKs'''

    sorted_articles = []
    sorted_headlines = []
    max_text_length = config.max_text_length
    max_summary_length = config.max_summary_length
    min_length = config.min_length
    unk_text_limit = config.unk_text_limit
    unk_summary_limit = 0

    for count, words in enumerate(int_rep_articles):
        if (len(int_rep_articles[count]) >= min_length and len(int_rep_articles[count]) <= max_text_length
            and unk_counter(int_rep_headlines[count], vocab_to_int) <= unk_summary_limit and
                    unk_counter(int_rep_articles[count], vocab_to_int) <= unk_text_limit):
            sorted_headlines.append(int_rep_headlines[count])
            sorted_articles.append(int_rep_articles[count])

    # Compare lengths to ensure they match
    print(len(sorted_headlines))
    print(len(sorted_articles))

    return sorted_articles, sorted_headlines


def get_wordnet_pos(treebank_tag):
    if treebank_tag.startswith('J'):
        return wordnet.ADJ
    elif treebank_tag.startswith('V'):
        return wordnet.VERB
    elif treebank_tag.startswith('N'):
        return wordnet.NOUN
    elif treebank_tag.startswith('R'):
        return wordnet.ADV
    else:
        return wordnet.NOUN


def normalize_text(text):
    cleaned = list()

    for line in text :
        word_pos = nltk.pos_tag(nltk.word_tokenize(line))
        lemm_words = [lmtzr(sw[0], get_wordnet_pos(sw[1])) for sw in word_pos]

        word = [x.lower() for x in lemm_words]
        cleaned.append(' '.join(word))

    return cleaned


def main():
    # Load data (deserialize)
    print("Loading data ......")
    with open(config.base_path + config.stories_pickle_filename, 'rb') as handle:
        all_stories = pickle.load(handle)

    # clean stories
    clean_articles = []
    clean_headlines = []
    for example in all_stories:
        example['article'] = clean_text(example['article'].split('\n'))
        clean_articles.append(' '.join(example['article']))
        example['headlines'] = clean_text(example['headlines'], remove_stopwords=False)
        clean_headlines.append(' '.join(example['headlines']))

    clean_articles = normalize_text(clean_articles)
    clean_headlines = normalize_text(clean_headlines)

    word_counts = {}
    count_words(word_counts, clean_articles)
    count_words(word_counts, clean_headlines)

    print("Total Stories : ", len(clean_headlines))
    print("Size of Vocabulary:", len(word_counts))


    print("creating embedding index .....")
    embeddings_index = {};
    vectorization(clean_articles, embeddings_index)
    vectorization(clean_headlines, embeddings_index)
    print('Word embeddings:', len(embeddings_index))

    # find out missing words and thr %
    missing_ratio, missing_words_count = missing_word_ratio(word_counts, embeddings_index)

    print("Number of words missing :", missing_words_count)
    print("Percent of words that are missing from vocabulary: {}%".format(missing_ratio))

    '''dictionary to convert words to integers - This is to found total words count that we get from aur corpus(input date)
    and out of that what % of words we would be using. This is after removing words that count less than threshold'''
    vocab_to_int = covert_vocab_to_int(word_counts, embeddings_index)

    word_embedding_matrix = create_combine_word_matrix(vocab_to_int, embeddings_index)

    # Apply convert_to_ints to clean_articles and clean_headlines
    print("Article Data")
    int_repr_articles, word_article_count, unk_article_count = convert_to_ints(clean_articles, vocab_to_int, eos=True)

    print("Headline Data")
    int_repr_headlines, word_headline_count, unk_headline_count = convert_to_ints(clean_headlines, vocab_to_int)

    lengths_articles = create_dataFrame(int_repr_articles)
    # lengths_headlines = create_dataFrame(int_repr_headlines)

    sorted_articles, sorted_headlines = sort_corplus(lengths_articles, int_repr_articles,
                                                     int_repr_headlines, vocab_to_int)




'''------- Read main ----------'''
main()
