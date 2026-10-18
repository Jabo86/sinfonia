import unittest
from src.blockchain import Block, Blockchain
import time

class TestBlockchain(unittest.TestCase):

    def test_create_genesis_block(self):
        blockchain = Blockchain()
        genesis_block = blockchain.create_genesis_block()
        self.assertEqual(genesis_block.index, 0)
        self.assertEqual(genesis_block.data, "Genesis Block")
        self.assertEqual(genesis_block.previous_hash, "0")

    def test_add_block(self):
        blockchain = Blockchain()
        genesis_block = blockchain.create_genesis_block()
        new_block = Block(1, time.time(), "New Block", genesis_block.hash)
        blockchain.add_block(new_block)
        self.assertEqual(len(blockchain.chain), 2)
        self.assertEqual(blockchain.chain[1].previous_hash, genesis_block.hash)

    def test_is_chain_valid(self):
        blockchain = Blockchain()
        genesis_block = blockchain.create_genesis_block()
        new_block = Block(1, time.time(), "New Block", genesis_block.hash)
        blockchain.add_block(new_block)
        self.assertTrue(blockchain.is_chain_valid())

    def test_invalid_block_hash(self):
        blockchain = Blockchain()
        genesis_block = blockchain.create_genesis_block()
        new_block = Block(1, time.time(), "New Block", genesis_block.hash)
        new_block.hash = "Invalid Hash"
        blockchain.add_block(new_block)
        self.assertFalse(blockchain.is_chain_valid())

    def test_invalid_previous_hash(self):
        blockchain = Blockchain()
        genesis_block = blockchain.create_genesis_block()
        new_block = Block(1, time.time(), "New Block", "Invalid Hash")
        blockchain.add_block(new_block)
        self.assertFalse(blockchain.is_chain_valid())

if __name__ == '__main__':
    unittest.main()
