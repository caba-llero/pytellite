import numpy as np


def skew(v: np.ndarray) -> np.ndarray:
    """Return the 3x3 skew-symmetric matrix (v_x) of a 3-element vector v."""
    return np.array([
        [0, -v[2], v[1]],
        [v[2], 0, -v[0]],
        [-v[1], v[0], 0]
    ])


class Quaternion:
    """A quaternion class for attitude representation and operations.

    The quaternion is stored as a 4x1 numpy array with scalar-last convention:
    [q1, q2, q3, q4].T where q4 is the scalar component.
    """

    def __init__(self, *args):
        """Initialize a quaternion from its 4 components.

        Args:
            Can accept either:
            - 4 individual numeric values: Quaternion(q1, q2, q3, q4)
            - A numpy array of shape (4,1) or (4,): Quaternion(array)
            - A 4-element list or tuple: Quaternion([q1, q2, q3, q4])

        Examples:
            quat1 = Quaternion(1, 2, 3, 4)  # Individual components
            quat2 = Quaternion([1, 2, 3, 4])  # List
            quat3 = Quaternion(np.array([1, 2, 3, 4]))  # Numpy array (4,)
            quat4 = Quaternion(np.array([[1], [2], [3], [4]]))  # Numpy array (4,1)
        """
        # Handle different input formats
        if len(args) == 4:
            # Four individual components
            q1, q2, q3, q4 = args
            self._q = np.array([q1, q2, q3, q4], dtype=float).reshape(4, 1)
        elif len(args) == 1:
            # Single array-like input
            value = args[0]
            if isinstance(value, (list, tuple)) and len(value) == 4:
                # Convert 4-element list/tuple to numpy array
                self._q = np.array(value, dtype=float).reshape(4, 1)
            elif isinstance(value, np.ndarray):
                # Handle numpy arrays
                if value.shape == (4,):
                    self._q = value.reshape(4, 1)
                elif value.shape == (4, 1):
                    self._q = value.copy()
                else:
                    raise ValueError("Quaternion must be a 4x1 or (4,) numpy array")
            else:
                raise ValueError("Single argument must be a 4-element array-like object")
        else:
            raise ValueError("Quaternion requires either 4 individual components or 1 array-like argument")

    @property
    def q(self) -> np.ndarray:
        """Get the quaternion vector."""
        return self._q

    @q.setter
    def q(self, value):
        """Set the quaternion vector.

        Args:
            value: Can be either:
                - A numpy array of shape (4,1) or (4,)
                - Four individual numeric values as a tuple/list/array
                - Four individual numeric values as separate arguments (not supported in setter)
        """
        # Handle different input formats
        if isinstance(value, (list, tuple)) and len(value) == 4:
            # Convert 4 individual values to numpy array
            q_array = np.array(value, dtype=float).reshape(4, 1)
        elif isinstance(value, np.ndarray):
            # Handle numpy arrays
            if value.shape == (4,):
                q_array = value.reshape(4, 1)
            elif value.shape == (4, 1):
                q_array = value
            else:
                raise ValueError("Quaternion must be a 4x1 or (4,) numpy array")
        else:
            raise ValueError("Quaternion must be a 4-element array-like object or numpy array")

        self._q = q_array.copy()

    @property
    def Psi(self) -> np.ndarray:
        """The Psi(q) function for quaternions.

        Output: np.ndarray of shape (4,3)
        Source: Markley (Eq. 2.87, p.38)"""
        q_flat = self._q.flatten()
        return np.array([
            [q_flat[3], q_flat[2], -q_flat[1]],
            [-q_flat[2], q_flat[3], q_flat[0]],
            [q_flat[1], -q_flat[0], q_flat[3]],
            [-q_flat[0], -q_flat[1], -q_flat[2]]
        ])

    @property
    def Xi(self) -> np.ndarray:
        """The Xi(q) function for quaternions.

        Output: np.ndarray of shape (4,3)
        Source: Markley (Eq. 2.88, p.38)"""
        q_flat = self._q.flatten()
        return np.array([
            [q_flat[3], -q_flat[2], q_flat[1]],
            [q_flat[2], q_flat[3], -q_flat[0]],
            [-q_flat[1], q_flat[0], q_flat[3]],
            [-q_flat[0], -q_flat[1], -q_flat[2]]
        ])

    @property
    def x(self) -> np.ndarray:
        """Quaternion (x) product matrix.

        Output: np.ndarray of shape (4,4)
        Usage: q1.q_x() @ q2.q
        Source: Markley (Eq. 2.85, p.38)"""
        return np.hstack((self.Psi, self._q))

    @property
    def n(self) -> 'Quaternion':
        """Get a normalized version of this quaternion.

        Returns:
            A new normalized Quaternion instance (original remains unchanged)
        """
        n = np.linalg.norm(self._q)
        if n == 0:
            # Return identity quaternion
            normalized_q = np.array([[0.0, 0.0, 0.0, 1.0]]).T
        else:
            normalized_q = self._q / n
        return Quaternion(normalized_q)

    def normalize_inplace(self) -> None:
        """Normalize the quaternion in-place."""
        n = np.linalg.norm(self._q)
        if n == 0:
            self._q = np.array([[0.0, 0.0, 0.0, 1.0]]).T
        else:
            self._q = self._q / n

    @property
    def norm(self) -> float:
        """Get the norm (magnitude) of the quaternion."""
        return np.linalg.norm(self._q)

    @property
    def is_normalized(self) -> bool:
        """Check if the quaternion is normalized."""
        return np.isclose(self.norm, 1.0)

    def __repr__(self) -> str:
        """Detailed string representation."""
        return f"Quaternion(q={self._q.flatten()}, norm={self.norm:.6f})"
