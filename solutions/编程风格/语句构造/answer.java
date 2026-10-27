public class source {
    public static int count(int x) {
        int res = 0;
        while (x > 0) {
            x -= (x & -x);
            ++res;
        }
        return res;
    }
}