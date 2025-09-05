from numba import njit
import numpy as np
from scipy.spatial.transform import Rotation as R
from scipy.spatial.transform import Slerp


@njit
def quat_psi(q: np.ndarray) -> np.ndarray:
    """The Psi(q) function for quaternions.

    Args:
        q: np.ndarray of shape (4,) or (4,1)

    Output: np.ndarray of shape (4,3)
    Source: Markley (Eq. 2.87, p.38)"""
    q_flat = q.flatten()
    return np.array([
        [q_flat[3], q_flat[2], -q_flat[1]],
        [-q_flat[2], q_flat[3], q_flat[0]],
        [q_flat[1], -q_flat[0], q_flat[3]],
        [-q_flat[0], -q_flat[1], -q_flat[2]]
    ])


@njit
def quat_xi(q: np.ndarray) -> np.ndarray:
    """The Xi(q) function for quaternions.

    Args:
        q: np.ndarray of shape (4,) or (4,1)

    Output: np.ndarray of shape (4,3)
    Source: Markley (Eq. 2.88, p.38)"""
    q_flat = q.flatten()
    return np.array([
        [q_flat[3], -q_flat[2], q_flat[1]],
        [q_flat[2], q_flat[3], -q_flat[0]],
        [-q_flat[1], q_flat[0], q_flat[3]],
        [-q_flat[0], -q_flat[1], -q_flat[2]]
    ])


@njit
def quat_multiply_cross_operator(q: np.ndarray) -> np.ndarray:
    """Quaternion ⊗ product matrix operator.

    Args:
        q: np.ndarray of shape (4,) or (4,1)

    Output: np.ndarray of shape (4,4)
    Usage in the context of quaternion multiplication: quat_multiply_cross_operator(q1) @ q2
    Source: Markley (Eq. 2.85, p.38)"""
    return np.hstack((quat_psi(q), q.reshape(4, 1)))


@njit
def quat_multiply_dot_operator(q: np.ndarray) -> np.ndarray:
    """Quaternion ⨀ product matrix operator.

    Args:
        q: np.ndarray of shape (4,) or (4,1)

    Output: np.ndarray of shape (4,4)
    Usage in the context of quaternion multiplication: quat_multiply_dot_operator(q1) @ q2
    Source: Markley (Eq. 2.86, p.38)"""
    return np.hstack((quat_xi(q), q.reshape(4, 1)))


@njit
def quat_normalize(q: np.ndarray) -> np.ndarray:
    """
    Get a normalized version of this quaternion.

    Args:
        q: np.ndarray of shape (4,) or (4,1)

    Returns:
        A new normalized quaternion (original remains unchanged)
    """
    n = np.linalg.norm(q)
    if n == 0:
        # Return identity quaternion
        normalized_q = np.array([0.0, 0.0, 0.0, 1.0])
    else:
        normalized_q = q.flatten() / n
    return normalized_q


@njit
def quat_norm(q: np.ndarray) -> float:
    """Get the norm (magnitude) of the quaternion."""
    return np.linalg.norm(q)


@njit
def quat_is_normalized(q: np.ndarray) -> bool:
    """Check if the quaternion is normalized."""
    return np.isclose(quat_norm(q), 1.0)


@njit
def quat_conj(q: np.ndarray) -> np.ndarray:
    """Get the conjugate of a quaternion."""
    q_flat = q.flatten()
    return np.array([-q_flat[0], -q_flat[1], -q_flat[2], q_flat[3]])


@njit
def quat_multiply_cross(q1: np.ndarray, q2: np.ndarray) -> np.ndarray:
    """Quaternion multiplication, defined as ⊗ operator from Markley.
    If the second argument is a vector, it is treated as a quaternion with a zero scalar component."""
    mat = quat_multiply_cross_operator(q1)
    # Always return a flat (4,) array for consistency with Numba
    if q2.shape == (3,) or q2.shape == (3, 1):
        v4 = np.zeros(4)
        v4[:3] = q2.flatten()
        return (mat @ v4).reshape(4,)
    return (mat @ q2.reshape(4,)).reshape(4,)


@njit
def quat_multiply_dot(q1: np.ndarray, q2: np.ndarray) -> np.ndarray:
    """Quaternion multiplication, defined as ⊙ operator from Markley.
    If the second argument is a vector, it is treated as a quaternion with a zero scalar component."""
    mat = quat_multiply_dot_operator(q1)
    # Always return a flat (4,) array for consistency with Numba
    if q2.shape == (3,) or q2.shape == (3, 1):
        v4 = np.zeros(4)
        v4[:3] = q2.flatten()
        return (mat @ v4).reshape(4,)
    return (mat @ q2.reshape(4,)).reshape(4,)


@njit
def quat_inv(q: np.ndarray) -> np.ndarray:
    """Inverse of a quaternion is the conjugate divided by the norm squared."""
    return quat_conj(q) / (quat_norm(q)**2)


def slerp(q0: np.ndarray, q1: np.ndarray, t: float) -> np.ndarray:
    """Spherical linear interpolation between two quaternions."""
    q0_n = quat_normalize(q0)
    q1_n = quat_normalize(q1)
    dot = np.dot(q0_n.flatten(), q1_n.flatten())
    if dot < 0:
        q1_n = -q1_n
        dot = -dot
    if dot > 0.9995:
        return (1 - t) * q0_n + t * q1_n

    theta = np.arccos(dot)
    s0 = np.sin(theta)
    w1 = np.sin((1 - t) * theta) / s0
    w2 = np.sin(t * theta) / s0
    return w1 * q0_n + w2 * q1_n


def slerp_array(t_sampled: np.ndarray, t0: np.ndarray, q0: np.ndarray) -> np.ndarray:
    """Spherical linear interpolation between many quaternions.
    q0: np.ndarray of size (4, n) where each column is a quaternion
    t_sampled: np.ndarray of size (n,)
    Output: np.ndarray of size (4, n) where each column is a quaternion
    """
    q = R.from_quat(q0.T)
    slerp = Slerp(t0, q)
    return slerp(t_sampled).as_euler('zyx', degrees=False).T


def slerp_quat_array(t_sampled: np.ndarray, t0: np.ndarray, q0: np.ndarray) -> np.ndarray:
    """Spherical linear interpolation returning quaternion components.
    
    Args:
        t_sampled: 1D array of sample times
        t0: 1D array of keyframe times
        q0: (4, N) quaternion keyframes with scalar-last convention [x, y, z, w]

    Returns:
        (4, M) array of interpolated quaternions [x, y, z, w] across t_sampled
    """
    rotations = R.from_quat(q0.T)
    interpolator = Slerp(t0, rotations)
    return interpolator(t_sampled).as_quat().T


def rotmatrix_to_quaternion(A: np.ndarray) -> np.ndarray:
    """
    Convert a rotation matrix to a quaternion.
    Source: Markley (Eq. 2.135, p.48)
    """
    trA = np.trace(A)
    A11 = A[0, 0]
    A22 = A[1, 1]
    A33 = A[2, 2]

    if max(trA, A11, A22, A33) == trA:
        q4 = np.sqrt(1 + trA) / 2
        q1 = (A[2, 1] - A[1, 2]) / (4 * q4)
        q2 = (A[0, 2] - A[2, 0]) / (4 * q4)
        q3 = (A[1, 0] - A[0, 1]) / (4 * q4)
    elif max(trA, A11, A22, A33) == A11:
        q1 = np.sqrt(1 + 2 * A11 - trA) / 2
        q2 = (A[0, 1] + A[1, 0]) / (4 * q1)
        q3 = (A[0, 2] + A[2, 0]) / (4 * q1)
        q4 = (A[1, 2] - A[2, 1]) / (4 * q1)
    elif max(trA, A11, A22, A33) == A22:
        q2 = np.sqrt(1 + 2 * A22 - trA) / 2
        q1 = (A[0, 1] + A[1, 0]) / (4 * q2)
        q3 = (A[1, 2] + A[2, 1]) / (4 * q2)
        q4 = (A[0, 2] - A[2, 0]) / (4 * q2)
    elif max(trA, A11, A22, A33) == A33:
        q3 = np.sqrt(1 + 2 * A33 - trA) / 2
        q1 = (A[0, 2] + A[2, 0]) / (4 * q3)
        q2 = (A[1, 2] + A[2, 1]) / (4 * q3)
        q4 = (A[0, 1] - A[1, 0]) / (4 * q3)

    return np.array([q1, q2, q3, q4])


def quat_to_rotmatrix(q: np.ndarray) -> np.ndarray:
    """Quaternion to rotation matrix
    Markley (Eq. 2.129, p.46)"""
    return quat_xi(q).T @ quat_psi(q)


def rotmatrix_to_euler313(A: np.ndarray) -> np.ndarray:
    theta = np.arccos(A[2, 2])  # pitch
    sigma = np.sign(np.sin(theta))

    phi = np.arctan2(sigma * A[2, 0], -sigma * A[2, 1])  # roll
    psi = np.arctan2(sigma * A[0, 2], sigma * A[1, 2])  # yaw

    return np.array([phi, theta, psi])


def rotmatrix_to_euler321(A: np.ndarray) -> np.ndarray:
    """Rotation matrix to Euler angles (ZYX sequence for roll, pitch, yaw).
    
    Output: np.ndarray with [roll, pitch, yaw]
    """
    pitch = np.arcsin(-A[2, 0])
    yaw = np.arctan2(A[1, 0], A[0, 0])
    roll = np.arctan2(A[2, 1], A[2, 2])
    return np.array([roll, pitch, yaw])


def quat_to_euler(q: np.ndarray) -> np.ndarray:
    """Quaternion to Euler angles (ZYX sequence for roll, pitch, yaw)"""
    # If q is a single quaternion (4,) or (4,1)
    if q.ndim == 1 or (q.ndim == 2 and q.shape[1] == 1):
        return rotmatrix_to_euler321(quat_to_rotmatrix(q))
    
    # If q is an array of quaternions (4, N)
    num_quats = q.shape[1]
    euler_angles = np.empty((3, num_quats))
    for i in range(num_quats):
        # Extract each quaternion
        q_i = q[:, i].reshape(4, 1)
        # Convert to Euler and store
        euler_angles[:, i] = rotmatrix_to_euler321(quat_to_rotmatrix(q_i)).flatten()
        
    return euler_angles
