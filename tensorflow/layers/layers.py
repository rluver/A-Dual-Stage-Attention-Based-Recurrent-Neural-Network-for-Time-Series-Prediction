import tensorflow as tf
from tensorflow.keras.layers import Input, LSTM, Layer, Dense, RepeatVector, Permute, Lambda


class NewLSTM(LSTM):
    def __init__(self, units, **kwargs):
        super(NewLSTM, self).__init__(**kwargs)
        self.lstm = LSTM(units=units, return_sequences=True, return_state=True)

    def call(self, x, training=False):
        _, hidden_state, cell_state = self.lstm(x)
        self.initial_state = [hidden_state, cell_state]

        return hidden_state, cell_state

    def reset_state(self, hidden_state, cell_state):
        self.initial_state = [hidden_state, cell_state]


class InputAttention(Layer):
    def __init__(self, units, **kwargs):
        super(InputAttention, self).__init__(**kwargs)
        self.w1 = Dense(units)
        self.w2 = Dense(units)
        self.v = Dense(1)

    def call(self, x, hidden_state, cell_state):
        query = tf.concat([hidden_state, cell_state], axis=-1)
        query = RepeatVector(x.shape[2])(query)

        x_permuted = Permute((2, 1))(x)

        score = tf.nn.tanh(self.w1(x_permuted) + self.w2(query))
        score = self.v(score)
        score = Permute((2, 1))(score)

        attention_weights = tf.nn.softmax(score, axis=-1)

        context_vector = attention_weights * x
        context_vector = tf.reduce_sum(context_vector, axis=-1)

        return context_vector, attention_weights


class Encoder(Layer):
    def __init__(self, units, seq_len, **kwargs):
        super(Encoder, self).__init__(**kwargs)
        self.seq_len = seq_len
        self.input_attention = InputAttention(seq_len)
        self.lstm = NewLSTM(units)
        self.initial_state = None
        self.a_t = None

    def call(self, x, hidden_state, cell_state, n, training=False):
        self.lstm.reset_state(hidden_state=hidden_state, cell_state=cell_state)

        a = tf.TensorArray(tf.float32, self.seq_len)
        for t in range(self.seq_len):
            x = Lambda(lambda x: x[:, t, :])(x)
            x = x[:, tf.newaxis, :]

            hidden_state, cell_state = self.lstm(x)
            self.a_t = self.input_attention(x, hidden_state, cell_state)

            a = a.write(t, self.a_t)

        a = tf.reshape(a.stack(), (-1, self.seq_len, n))
        output = tf.multiply(x, a)

        return output


class TemporalAttention(Layer):
    def __init__(self, units, **kwargs):
        super(TemporalAttention, self).__init__(**kwargs)
        self.w1 = Dense(units)
        self.w2 = Dense(units)
        self.v = Dense(1)

    def call(self, hidden_state, cell_state, encoder_hidden_state):
        query = tf.concat([hidden_state, cell_state], axis=-1)
        query = RepeatVector(encoder_hidden_state.shape[1])(query)

        score = tf.nn.tanh(self.w1(encoder_hidden_state) + self.w2(query))
        score = self.v(score)

        attention_weights = tf.nn.softmax(score, axis=-1)

        return attention_weights


class Decoder(Layer):
    def __init__(self, units, seq_len, **kwargs):
        super(Decoder, self).__init__(**kwargs)
        self.seq_len = seq_len
        self.temporal_attention = TemporalAttention(units)
        self.lstm = NewLSTM(units)
        self.dense = Dense(1)
        self.encoder_dim = kwargs.get('encoder_dim')
        self.decoder_dim = kwargs.get('decoder_dim')
        self.context_vector
        self.b_t = None

    def call(self, x, hidden_state, cell_state, encoder_hidden_state, training=False):
        self.lstm.reset_state(hidden_state=hidden_state, cell_state=cell_state)
        context_vector = tf.zeros((encoder_hidden_state.shape[0], 1, self.encoder_dim))
        decoder_hidden_state = tf.zeros(encoder_hidden_state.shape[0], self.decoder_dim)

        for t in range(self.seq_len - 1):
            l = Lambda(lambda x: x[:, t, :])(x)
            l = l[:, tf.newaxis, :]
            l = tf.concat([l, context_vector], axis=-1)
            l = self.dense(l)

            hidden_state, cell_state = self.lstm(l)
            self.b_t = self.temporal_attention(hidden_state, cell_state, encoder_hidden_state)
            context_vector = tf.matmul(self.b_t, encoder_hidden_state, transpose_a=True)

        output = tf.concat([hidden_state[:, tf.newaxis, :], self.context_vector], axis=-1)

        return output
