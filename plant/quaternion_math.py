import numpy as np

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
        """Quaternion ⊗ product matrix.

        Output: np.ndarray of shape (4,4)
        Usage in the context of quaternion multiplication: q1.x() @ q2.q
        Source: Markley (Eq. 2.85, p.38)"""
        return np.hstack((self.Psi, self._q))

    @property
    def ddot(self) -> np.ndarray:
        """Quaternion ⨀ product matrix.

        Output: np.ndarray of shape (4,4)
        Usage in the context of quaternion multiplication: q1.ddot() @ q2.q
        Source: Markley (Eq. 2.86, p.38)"""
        return np.hstack((self.Xi, self._q))

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

    @property 
    def conj(self) -> 'Quaternion':
        return Quaternion(-self._q[0], -self._q[1], -self._q[2], self._q[3])

    def __repr__(self) -> str:
        """Detailed string representation."""
        return f"Quaternion(q={self._q.flatten()}, norm={self.norm:.6f})"

    def __add__(self, other: 'Quaternion') -> 'Quaternion':
        return Quaternion(self._q + other._q)

    def __sub__(self, other: 'Quaternion') -> 'Quaternion':
        return Quaternion(self._q - other._q)
    
    def __mul__(self, other):
        """Quaternion multiplication, defined as ⊗ operator from Markley.
        If the second argument is a vector, it is treated as a quaternion with a zero scalar component."""
        if isinstance(other, Quaternion):
            return Quaternion(self.x @ other._q)
        elif isinstance(other, np.ndarray):
            # Handle 3x1 or (3,) vector
            if other.shape == (3,) or other.shape == (3,1):
                # Make it a 4x1 array with 4th element zero
                v4 = np.zeros((4,1))
                v4[:3,0] = other.flatten()
                return Quaternion(self.x @ v4)
            else:
                raise ValueError("Can only multiply Quaternion by a 3-element vector")
        elif np.isscalar(other):
            return Quaternion(self._q * other)
        else:
            return NotImplemented

    def __pow__(self, other):
        """Quaternion multiplication, defined as ⊙ operator from Markley.
        If the second argument is a vector, it is treated as a quaternion with a zero scalar component."""
        if isinstance(other, Quaternion):
            return Quaternion(self.ddot @ other._q)
        elif isinstance(other, np.ndarray):
            # Handle 3x1 or (3,) vector
            if other.shape == (3,) or other.shape == (3,1):
                # Make it a 4x1 array with 4th element zero
                v4 = np.zeros((4,1))
                v4[:3,0] = other.flatten()
                return Quaternion(self.ddot @ v4)
            else:
                raise ValueError("Can only multiply Quaternion by a 3-element vector")
        elif np.isscalar(other):
            return Quaternion(self._q * other)
        else:
            return NotImplemented

    def __invert__(self) -> 'Quaternion': # inverse of a quaternion is the conjugate divided by the norm squared
        return self.conj / self.norm**2
    
    def __truediv__(self, other: float) -> 'Quaternion': # scalar division
        return Quaternion(self._q / other)

    def __rmul__(self, other) -> 'Quaternion': # scalar multiplication
        if isinstance(other, np.ndarray):   # Handle 3x1 or (3,) vector
            if other.shape == (3,) or other.shape == (3,1):  # Make it a 4x1 array with 4th element zero              
                v4 = np.zeros((4,1))
                v4[:3,0] = other.flatten()
                return Quaternion(self.x @ v4)
            else:
                raise ValueError("Can only multiply Quaternion by a 3-element vector")
        elif np.isscalar(other):
            return Quaternion(self._q * other)
        else:
            return NotImplemented
    
    def __eq__(self, other: 'Quaternion') -> bool:
        return np.allclose(self._q, other._q)
    

    
def rotmatrix_to_quaternion(A: np.ndarray) -> Quaternion:
    """
    Convert a rotation matrix to a quaternion.
    Source: Markley (Eq. 2.135, p.48)
    """
    trA = np.trace(A)
    A11 = A[0,0]
    A22 = A[1,1]
    A33 = A[2,2]

    if max(trA, A11, A22, A33) == trA:
        q4 = np.sqrt(1 + trA) / 2
        q1 = (A[2,1] - A[1,2]) / (4 * q4)
        q2 = (A[0,2] - A[2,0]) / (4 * q4)
        q3 = (A[1,0] - A[0,1]) / (4 * q4)
    elif max(trA, A11, A22, A33) == A11:
        q1 = np.sqrt(1 + 2 * A11 - trA) / 2
        q2 = (A[0,1] + A[1,0]) / (4 * q1)
        q3 = (A[0,2] + A[2,0]) / (4 * q1)
        q4 = (A[1,2] - A[2,1]) / (4 * q1)
    elif max(trA, A11, A22, A33) == A22:
        q2 = np.sqrt(1 + 2 * A22 - trA) / 2
        q1 = (A[0,1] + A[1,0]) / (4 * q2)
        q3 = (A[1,2] + A[2,1]) / (4 * q2)
        q4 = (A[0,2] - A[2,0]) / (4 * q2)
    elif max(trA, A11, A22, A33) == A33:
        q3 = np.sqrt(1 + 2 * A33 - trA) / 2
        q1 = (A[0,2] + A[2,0]) / (4 * q3)
        q2 = (A[1,2] + A[2,1]) / (4 * q3)
        q4 = (A[0,1] - A[1,0]) / (4 * q3)   

    return Quaternion(q1, q2, q3, q4)

def quat_to_rotmatrix(q: Quaternion) -> np.ndarray:
    """Quaternion to rotation matrix
    Markley (Eq. 2.129, p.46)"""
    return q.Xi.T @ q.Psi


def rotmatrix_to_euler313(A: np.ndarray) -> np.ndarray:    
    theta = np.arccos(A[2,2]) # pitch
    sigma = np.sign(np.sin(theta))

    phi = np.arctan2(sigma*A[2,0], -sigma*A[2,1]) # roll
    psi = np.arctan2(sigma*A[0,2], sigma*A[1,2]) # yaw

    return np.array([phi, theta, psi])

def rotmatrix_to_euler321(A: np.ndarray) -> np.ndarray:
    """Rotation matrix to Euler angles (ZYX sequence for roll, pitch, yaw).
    
    Output: np.ndarray with [roll, pitch, yaw]
    """
    pitch = np.arcsin(-A[2,0])
    yaw = np.arctan2(A[1,0], A[0,0])
    roll = np.arctan2(A[2,1], A[2,2])
    return np.array([roll, pitch, yaw])



def quat_to_euler(q: Quaternion) -> np.ndarray:
    """Quaternion to Euler angles (ZYX sequence for roll, pitch, yaw)"""
    return rotmatrix_to_euler321(quat_to_rotmatrix(q))
