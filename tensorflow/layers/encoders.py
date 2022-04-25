import tensorflow as tf
from tensorflow.keras.layers import Input, LSTM, Layer, Dense, RepeatVector, Permute, Lambda
from tensorflow.keras.models import Model


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
