#!/usr/bin/env python3
"""Test script for quaternion inversion operator."""

import numpy as np
from plant.quaternion_math import Quaternion

def test_quaternion_inversion():
    """Test that the ~ operator works for quaternion inversion."""
    print("Testing Quaternion Inversion (~ operator)")
    print("=" * 50)

    # Create a test quaternion
    q = Quaternion([1, 2, 3, 4])
    print(f'Original quaternion: {q}')
    print(f'Components: {q._q.flatten()}')
    print(f'Norm: {q.norm:.6f}')

    # Test inversion
    try:
        q_inv = ~q
        print(f'\nInverted quaternion: {q_inv}')
        print(f'Inverted components: {q_inv._q.flatten()}')
        print(f'Inverted norm: {q_inv.norm:.6f}')

        # Verify: q * q_inv should be close to identity
        product = q * q_inv
        print(f'\nq * q_inv: {product}')
        print(f'Product components: {product._q.flatten()}')
        print(f'Product norm: {product.norm:.6f}')

        # Check if product is close to identity [0, 0, 0, 1]
        identity = np.array([0, 0, 0, 1])
        diff = np.abs(product._q.flatten() - identity)
        print(f'\nDifference from identity: {diff}')
        print(f'Max difference: {np.max(diff):.6f}')

        if np.allclose(product._q.flatten(), identity, atol=1e-10):
            print('\n✅ SUCCESS: q * q_inv ≈ identity quaternion')
        else:
            print('\n❌ FAILURE: q * q_inv is not close to identity')

    except Exception as e:
        print(f'\n❌ ERROR: {e}')
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_quaternion_inversion()
